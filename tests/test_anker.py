"""FM27-Anker: Berechnung aus dem Pool (Perzentile), Spiegelung bei 'niedriger ist besser', Verwerfen, Anwenden."""

import benchmark as b
import common
import ligen
import numpy as np
import pandas as pd
import pytest

LG = ligen.Ligen.laden()


def stat(name, schlecht, ok, gut, art="pct"):
    return {"stat": name, "art": art, "label": name, "schlecht": schlecht, "ok": ok, "gut": gut}


def cfg_with(*stats):
    return {
        "defaults": {"min_minuten": 900},
        "profile": {"p": {"name": "p", "positionen": [{"pos": "ST"}], "stats": list(stats)}},
    }


def pool_df(n=1000, league="Bundesliga", **cols):
    d = {
        "position": "ST (C)",
        "minutes": 1500,
        "team": "Senior Team",
        "datenbasis": "voll",
        "league": league,
    }
    return pd.DataFrame({**d, **{k: v for k, v in cols.items()}}, index=range(n))


def test_anchors_are_the_requested_percentiles_of_the_pool():
    x = np.linspace(0, 100, 1001)
    df = pool_df(len(x), x=x)
    res = b.berechne_anker(
        df, cfg_with(stat("x", 10, 50, 90)), LG, "Gut", {"schlecht": 25, "ok": 55, "gut": 90}
    )
    a = res["p"]["stats"]["x"]
    assert (a["schlecht"], a["ok"], a["gut"]) == pytest.approx((25, 55, 90))
    assert a["n"] == 1001 and res["p"]["n_pool"] == 1001


def test_lower_is_better_mirrors_the_percentiles():
    x = np.linspace(0, 100, 1001)
    df = pool_df(len(x), x=x)
    res = b.berechne_anker(
        df, cfg_with(stat("x", 90, 50, 10)), LG, "Gut", {"schlecht": 25, "ok": 55, "gut": 90}
    )
    a = res["p"]["stats"]["x"]
    assert (a["schlecht"], a["ok"], a["gut"]) == pytest.approx(
        (75, 45, 10)
    )  # schlecht > ok > gut bleibt


def test_non_separating_or_thin_stats_are_dropped_with_reason():
    df = pool_df(500, x=np.zeros(500), y=np.linspace(0, 1, 500))
    cfg = cfg_with(stat("x", 1, 2, 3), stat("y", 0, 1, 2), stat("fehlt", 0, 1, 2))
    res = b.berechne_anker(df, cfg, LG, "Gut")
    assert "x" in res["p"]["verworfen"] and "trennscharf" in res["p"]["verworfen"]["x"]
    assert "y" in res["p"]["stats"]
    assert "fehlt" in res["p"]["verworfen"] and "nur 0 Werte" in res["p"]["verworfen"]["fehlt"]


def test_pool_filters_tier_senior_minutes_data_basis_and_position():
    base = pool_df(1, x=1.0).iloc[0].to_dict()
    rows = [
        {**base, "name": "ok"},
        {
            **base,
            "name": "niedrige_liga",
            "league": "Sky Bet League One",
        },  # Recht gut < Gut -> raus
        {**base, "name": "ohne_stufe", "league": "Amateurliga"},
        {**base, "name": "reserve", "team": "Reserves"},
        {**base, "name": "wenig_min", "minutes": 300},
        {**base, "name": "reduziert", "datenbasis": "reduziert"},
        {**base, "name": "falsche_pos", "position": "D (C)"},
        {**base, "name": "zweite_liga", "league": "2. Bundesliga"},  # Gut -> drin
    ]
    pool = b.anker_pool(
        pd.DataFrame(rows),
        cfg_with(stat("x", 0, 1, 2))["profile"]["p"],
        {"min_minuten": 900},
        LG,
        "Gut",
    )
    assert sorted(pool["name"]) == ["ok", "zweite_liga"]


def test_apply_replaces_anchors_and_removes_stats_without_anchor():
    prof = cfg_with(stat("a", 0, 1, 2), stat("b", 0, 1, 2))["profile"]["p"]
    neu = b.anker_anwenden(prof, {"stats": {"a": {"schlecht": 10, "ok": 20, "gut": 30, "n": 5}}})
    assert [s["stat"] for s in neu["stats"]] == ["a"]
    assert (neu["stats"][0]["schlecht"], neu["stats"][0]["gut"]) == (10, 30)
    assert [s["stat"] for s in prof["stats"]] == ["a", "b"] and prof["stats"][0][
        "gut"
    ] == 2  # Original unverändert
    assert [s["stat"] for s in b.anker_anwenden(prof, None)["stats"]] == []


def test_generated_anchor_file_matches_profiles_and_is_ordered():
    anker = common.load_yaml("anker_fm27.yaml")
    prof = common.load_yaml("profile.yaml")["profile"]
    assert anker["meta"]["perzentile"] == {"schlecht": 25, "ok": 55, "gut": 90}
    assert set(anker["profile"]) == set(prof)
    for pid, p in anker["profile"].items():
        known = {s["stat"] for s in prof[pid]["stats"]}
        assert set(p["stats"]) | set(p["verworfen"]) == known, pid
        for st, v in p["stats"].items():
            assert (v["schlecht"] < v["ok"] < v["gut"]) or (v["schlecht"] > v["ok"] > v["gut"]), (
                pid,
                st,
            )
