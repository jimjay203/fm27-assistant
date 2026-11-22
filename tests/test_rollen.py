"""Rollen-Score: gewichtetes Mittel, Anker je Gruppe, Rollenbewertung und Konsistenz der Taktik-Slots."""

import benchmark as b
import common
import ligen
import numpy as np
import pandas as pd
import pytest
import rollen

RK = common.load_yaml("rollen_kpis.yaml")
SLOTS = common.load_yaml("taktik_slots.yaml")["slots"]
LG = ligen.Ligen.laden()


def test_weighted_mean_uses_available_blocks_and_requires_coverage():
    idx = [0, 1, 2]
    parts = {
        "a": pd.Series([100.0, 100.0, np.nan], index=idx),
        "b": pd.Series([0.0, np.nan, np.nan], index=idx),
    }
    w = {"a": 3.0, "b": 1.0}
    out = rollen._gewichtet(parts, w, 0.6, idx)
    assert out[0] == pytest.approx(75)  # (3*100 + 1*0) / 4
    assert out[1] == pytest.approx(100)  # nur a: Gewicht 3 von 4 = 75 % >= 60 %
    assert np.isnan(out[2])  # nichts vorhanden
    strict = rollen._gewichtet(parts, w, 0.9, idx)
    assert np.isnan(strict[1])  # 75 % < 90 %
    assert rollen._gewichtet({}, w, 0.6, idx).isna().all()


def mini_rk():
    return {
        "gewichtung_je_gruppe": {"st": "standard"},
        "phasen_gewicht": {"mit": 0.5, "ohne": 0.5},
        "positionsgruppen": {"st": [{"pos": "ST"}]},
        "bausteine": {
            "tore": {"name": "t", "stats": [{"stat": "x", "art": "pct"}]},
            "fouls": {"name": "f", "stats": [{"stat": "f", "art": "pct", "richtung": "niedrig"}]},
        },
        "rollen": {
            "Mit": {
                "phase": "mit",
                "gruppe": "st",
                "bausteine": {"tore": 1},
                "verlaesslichkeit": "mittel",
            },
            "Ohne": {
                "phase": "ohne",
                "gruppe": "st",
                "bausteine": {"fouls": 1},
                "verlaesslichkeit": "mittel",
            },
        },
    }


def pool(n=400):
    x = np.linspace(0, 100, n)
    return pd.DataFrame(
        {
            "position": "ST (C)", "minutes": 1500, "team": "Senior Team", "datenbasis": "voll",
            "league": "Bundesliga", "x": x, "f": x[::-1], "club": "A", "own": False,
        }
    )  # fmt: skip


def test_group_anchors_follow_percentiles_and_mirror_lower_is_better():
    rk = mini_rk()
    specs = rollen.statistik_specs(rk, ["Mit", "Ohne"])
    assert specs["st"]["f"]["niedrig"] and not specs["st"]["x"]["niedrig"]
    anker = rollen.anker_je_gruppe(pool(), rk, specs, LG, {"min_minuten": 900})["st"]
    x, f = anker["stats"]["x"], anker["stats"]["f"]
    assert (x["schlecht"], x["ok"], x["gut"]) == pytest.approx((25, 55, 90), abs=0.5)
    assert (f["schlecht"], f["ok"], f["gut"]) == pytest.approx(
        (75, 45, 10), abs=0.5
    )  # gespiegelt, schlecht > ok > gut


def test_pair_score_is_mean_of_both_roles_and_ranks_the_better_player_higher():
    rk = mini_rk()
    specs = rollen.statistik_specs(rk, ["Mit", "Ohne"])
    df = pool()
    anker = rollen.anker_je_gruppe(df, rk, specs, LG, {"min_minuten": 900})
    ref = {"st": {}}
    spieler = pd.DataFrame(
        {"x": [95.0, 5.0], "f": [2.0, 98.0], "minutes": [1500, 1500]}, index=["gut", "schlecht"]
    )
    out = rollen.paar_bewerten(spieler, "Mit", "Ohne", rk, anker, ref, {})
    assert out.loc["gut", "mit"] == pytest.approx(100) and out.loc["gut", "ohne"] == pytest.approx(
        100
    )
    assert out.loc["schlecht", "mit"] == pytest.approx(0) and out.loc[
        "schlecht", "ohne"
    ] == pytest.approx(0)
    mixed = pd.DataFrame({"x": [95.0], "f": [98.0], "minutes": [1500]})
    assert rollen.paar_bewerten(mixed, "Mit", "Ohne", rk, anker, ref, {}).loc[
        0, "paar"
    ] == pytest.approx(50)
    assert out["vs_top"].isna().all()  # ohne Topclub-Referenz kein vs_top


def test_stats_without_anchor_are_skipped_and_role_needs_enough_blocks():
    rk = mini_rk()
    specs = rollen.statistik_specs(rk, ["Mit", "Ohne"])
    anker = rollen.anker_je_gruppe(
        pool(50), rk, specs, LG, {"min_minuten": 900}
    )  # zu wenig Werte (< 100)
    assert anker["st"]["stats"] == {} and "x" in anker["st"]["verworfen"]
    s, _t, _d = rollen.rolle_bewerten(pd.DataFrame({"x": [1.0]}), "Mit", rk, anker["st"], {})
    assert s.isna().all()


def test_taktik_slots_reference_existing_roles_with_matching_phases():
    assert len(SLOTS) == 11
    for name, s in SLOTS.items():
        mit, ohne = rollen.aufloesen(s["mit"], RK), rollen.aufloesen(s["ohne"], RK)
        assert RK["rollen"][mit]["phase"] in ("mit", "std"), (
            f"{name}: {mit} ist keine Rolle mit Ball"
        )
        assert RK["rollen"][ohne]["phase"] in ("ohne", "std"), (
            f"{name}: {ohne} ist keine Rolle ohne Ball"
        )
        assert RK["rollen"][mit]["gruppe"] == RK["rollen"][ohne]["gruppe"], name


def test_fm27_role_alias_points_to_an_existing_source_role():
    assert (
        rollen.aufloesen("Spielaufbauender Innenverteidiger", RK)
        == "Ballspielender Innenverteidiger"
    )
    assert rollen.aufloesen("Zielspieler", RK) == "Zielspieler"  # ohne Alias unverändert
    for alias, ziel in RK["alias_rollen"].items():
        assert alias not in RK["rollen"] and ziel in RK["rollen"], alias
    assert SLOTS["IV l"]["mit"] == "Spielaufbauender Innenverteidiger"


def test_group_weighting_schemes_exist_in_ligen_yaml_and_split_attack_defence():
    assert set(RK["gewichtung_je_gruppe"]) == set(RK["positionsgruppen"])
    assert all(v in LG.schemata() for v in RK["gewichtung_je_gruppe"].values())
    mild = {g for g, v in RK["gewichtung_je_gruppe"].items() if v == "mild"}
    assert mild == {"tw", "iv", "av", "fv"}
    assert b.position_ok("ST (C)", RK["positionsgruppen"]["st"])
