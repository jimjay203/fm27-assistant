"""Fair Value, role_score-Abdeckung und Konsistenz der produktiven rollen.yaml."""

import common
import fairvalue
import numpy as np
import pandas as pd
import pytest
import value

DEFAULTS = {"fv_min_n": 50, "fv_ratio_min": 2.0, "fv_liga_min_n": 10}


def synth(n=200, seed=1):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "rollen_score": rng.uniform(0, 100, n),
            "age": rng.integers(18, 35, n),
            "league": ["A"] * (n // 2) + ["B"] * (n - n // 2),
            "club_country": "X",
            "ingame_date": "2026-12-01",
            "contract_end": pd.to_datetime("2026-12-01")
            + pd.to_timedelta(rng.uniform(0.2, 4.5, n) * 365.25, unit="D"),
        }
    )
    years = fairvalue.remaining_years(df)
    a = (df["age"] - 25) / 5
    p = df["rollen_score"] / 100
    expiring = -0.5 * (years < 1) - 0.2 * ((years >= 1) & (years < 2))
    logv = 5.0 + 1.5 * p - 0.3 * a**2 + expiring + np.where(df["league"] == "A", 0.4, 0.0)
    df["value"] = 10**logv
    return df


def test_recovers_synthetic_value_and_flags_cheap_player():
    df = synth()
    df.loc[0, "value"] /= 3  # FM bewertet diesen Spieler zu niedrig
    out, info = fairvalue.add_fair_value(df, df, DEFAULTS)
    assert info["ok"] and info["r2"] > 0.95
    assert out.loc[0, "fv_ratio"] > 2.0 and bool(out.loc[0, "moneyball"])
    assert out.loc[1:, "moneyball"].sum() == 0  # alle anderen liegen nahe am Modell


def test_too_few_players_leaves_columns_empty():
    df = synth(n=30)
    out, info = fairvalue.add_fair_value(df, df, DEFAULTS)
    assert not info["ok"] and "30" in info["grund"]
    assert out["fair_value"].isna().all() and not out["moneyball"].any()


def test_small_league_falls_back_to_global_median():
    df = synth()
    med, glob = fairvalue.league_medians(df, min_n=1000)
    assert med == {} and np.isfinite(glob)
    _, info = fairvalue.add_fair_value(df, df, DEFAULTS | {"fv_liga_min_n": 1000})
    assert info["ok"]  # läuft ohne Liga-Medianeffekt durch


def test_missing_contract_end_gives_no_fair_value_for_that_player():
    df = synth()
    df.loc[5, "contract_end"] = pd.NaT
    out, _ = fairvalue.add_fair_value(df, df, DEFAULTS)
    assert np.isnan(out.loc[5, "fair_value"]) and not out.loc[5, "moneyball"]


def test_role_score_coverage():
    df = pd.DataFrame({"a_pctl": [80.0, 80.0], "b_pctl": [60.0, np.nan]})
    kpis = {"a": 1, "b": 1}
    strict = value.role_score(df, kpis)
    assert strict[0] == 70 and np.isnan(strict[1])
    relaxed = value.role_score(df, kpis, min_cover=0.5)
    assert relaxed[1] == 80  # Mittel über vorhandene KPIs
    assert np.isnan(value.role_score(df, {"a": 1, "b": 3}, min_cover=0.5)[1])  # nur 25 % Gewicht


def test_productive_rollen_yaml_kpis_map_to_known_stats():
    rollen = common.load_yaml("rollen.yaml")
    spalten = common.load_yaml("spalten.yaml")
    live = common.load_yaml("live_spalten.yaml")
    known = {
        (v if isinstance(v, str) else v["name"]) for v in spalten["spalten"].values()
    } | set(spalten["abgeleitet"]) | {s["name"] for s in live["stats"].values()}  # fmt: skip
    known |= {q["name"] for q in live["quoten"]}
    for name, role in rollen["rollen"].items():
        if not name.startswith("gruppe_"):
            continue  # stuermer_abschluss ist Platzhalter (TODO(export)) und wird separat gepflegt
        for kpi in role["kpis"]:
            base = kpi.removesuffix("_p90")
            assert kpi in known or base in known, f"{name}: KPI {kpi} ist kein gemappter Stat"
        attrs = {
            (v if isinstance(v, str) else v["name"])[5:]
            for v in spalten["spalten"].values()
            if str(v if isinstance(v, str) else v["name"]).startswith("attr_")
        }
        assert set(role["attribute_prior"]) <= attrs, f"{name}: unbekanntes Attribut"
    assert pytest.approx(0.6) == rollen["rollen"]["gruppe_st"]["min_abdeckung"]


def test_moneyball_needs_minimum_fair_value():
    df = synth()
    df["value"] /= 1e4  # alles winzig bewertet: Verhältnis passt, Fair Value liegt unter dem Boden
    df.loc[0, "value"] /= 3
    out, info = fairvalue.add_fair_value(df, df, DEFAULTS)
    assert info["ok"] and out.loc[0, "fv_ratio"] > 2.0
    assert not out["moneyball"].any()
    out, _ = fairvalue.add_fair_value(df, df, DEFAULTS | {"fv_min_fair": 0})
    assert bool(out.loc[0, "moneyball"])


def test_moneyball_needs_deviation_beyond_model_noise():
    rng = np.random.default_rng(3)
    df = synth()
    df["value"] *= 10 ** rng.normal(0, 0.6, len(df))  # Rauschen wie auf echten Daten (Faktor ~4)
    df.loc[0, "value"] /= 2.5  # 2,5x günstiger: über ratio_min, aber im Rauschen
    out, info = fairvalue.add_fair_value(df, df, DEFAULTS)
    assert info["rmse"] > 0.4
    assert out["fv_z"].notna().all()
    flagged = out[out["moneyball"]]
    assert (flagged["fv_z"] >= 1.5).all() and (flagged["fv_ratio"] >= 2.0).all()
    assert len(flagged) < 0.1 * len(out)  # nur wenige, nicht jeder zweite Spieler
    lenient, _ = fairvalue.add_fair_value(df, df, DEFAULTS | {"fv_z_min": 0})
    assert lenient["moneyball"].sum() > flagged.shape[0]  # z-Bedingung filtert tatsächlich


def test_long_contract_is_not_rewarded():
    df = synth()
    long_ = df.copy()
    long_["contract_end"] = pd.to_datetime("2026-12-01") + pd.Timedelta(days=int(4.9 * 365.25))
    a, _ = fairvalue.add_fair_value(df, df, DEFAULTS)
    b, _ = fairvalue.add_fair_value(long_, df, DEFAULTS)
    assert b["fair_value"].max() < 3 * df["value"].max()  # kein Explodieren durch lange Verträge
    exp = df["contract_end"] < pd.to_datetime("2027-12-01")
    assert a.loc[exp, "fair_value"].median() < a.loc[~exp, "fair_value"].median()
