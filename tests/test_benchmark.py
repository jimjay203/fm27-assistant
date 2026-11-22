"""Benchmark-Score: Interpolation, Richtung, Positionsregeln, Abdeckung und Konsistenz von profile.yaml."""

import benchmark as b
import common
import numpy as np
import pandas as pd
import pytest

CFG = common.load_yaml("profile.yaml")
SP_UP = {"stat": "x", "art": "pct", "schlecht": 10, "ok": 20, "gut": 40}
SP_DOWN = {
    "stat": "x",
    "art": "pct",
    "schlecht": 2.0,
    "ok": 1.0,
    "gut": 0.5,
}  # niedriger ist besser


def sc(values, spec):
    return b.stat_scores(pd.Series(values, dtype=float), spec).tolist()


def test_scores_are_piecewise_linear_and_clamped():
    assert sc([10, 20, 40], SP_UP) == [0, 50, 100]
    assert sc([15, 30], SP_UP) == [25, 75]
    assert sc([-5, 99], SP_UP) == [0, 100]  # geklemmt


def test_lower_is_better_when_poor_is_larger_than_good():
    assert sc([2.0, 1.0, 0.5], SP_DOWN) == [0, 50, 100]
    assert sc([1.5, 0.1, 3.0], SP_DOWN) == [25, 100, 0]


def test_missing_value_stays_missing():
    assert np.isnan(sc([np.nan], SP_UP)[0])


def test_positions_english_and_german_export_codes():
    assert b.position_ok("D (RC), DM", [{"pos": "D", "seiten": ["C"]}])
    assert not b.position_ok("D (R)", [{"pos": "D", "seiten": ["C"]}])
    assert b.position_ok("V (Z)", [{"pos": "D", "seiten": ["C"]}])  # Z = zentral
    assert b.position_ok("V/FV (R), OM (L)", [{"pos": "WB"}])  # FV = Wing-Back
    assert b.position_ok("TW", [{"pos": "GK"}]) and b.position_ok("ST (C)", [{"pos": "ST"}])
    assert not b.position_ok("DM", [{"pos": "D", "seiten": ["C"]}])
    assert b.position_ok("DM", [{"pos": "DM"}, {"pos": "M", "seiten": ["C"]}])
    assert not b.position_ok(None, [{"pos": "ST"}])


def test_score_profile_filters_minutes_and_requires_coverage():
    prof = CFG["profile"]["stuermer_torjaeger"]
    n = len(prof["stats"])
    base = {"position": "ST (C)", "minutes": 1800, "kopfbaelle_gewonnen": 130, "dribblings": 70,
            "npxg": 14.0, "schuesse_aufs_tor": 40.0, "konversionsrate_pct": 30.0}  # fmt: skip
    df = pd.DataFrame(
        [
            {"name": "gut", **base},
            {"name": "wenig_min", **base, "minutes": 300},
            {"name": "andere_pos", **base, "position": "D (C)"},
            {"name": "luecken", **{k: v for k, v in base.items() if k != "npxg"}},  # 4 von 5 = 80 %
            {
                "name": "zu_luecken",
                "position": "ST (C)",
                "minutes": 1800,
                "npxg": 14.0,
                "dribblings": 70,
            },  # 2 von 5
        ]
    )
    out = b.score_profile(df, prof, CFG["defaults"]).set_index("name")
    assert set(out.index) == {"gut", "luecken", "zu_luecken"}
    assert out.loc["gut", "n_stats"] == n and out.loc["gut", "score"] > 90
    assert out.loc["luecken", "n_stats"] == n - 1 and not np.isnan(out.loc["luecken", "score"])
    assert np.isnan(out.loc["zu_luecken", "score"])  # unter min_abdeckung


def test_p90_stats_are_divided_by_minutes():
    df = pd.DataFrame({"minutes": [900, 1800], "klaerungen": [9, 9]})
    v = b.stat_values(df, {"stat": "klaerungen", "art": "p90"})
    assert v.tolist() == [0.9, 0.45]


def test_calibration_reports_percentile_of_anchors():
    prof = {"name": "t", "positionen": [{"pos": "ST"}],
            "stats": [{"stat": "x", "art": "pct", "label": "x", "schlecht": 10, "ok": 50, "gut": 90}]}  # fmt: skip
    df = pd.DataFrame({"position": "ST (C)", "minutes": 1000, "x": np.arange(0, 100, 1.0)})
    cal = b.calibration(df, prof, {"min_minuten": 900}).iloc[0]
    assert cal["schlecht_perzentil"] == pytest.approx(10.5, abs=1)
    assert cal["gut_perzentil"] == pytest.approx(90.5, abs=1)


def test_profile_yaml_stats_exist_and_anchors_are_ordered():
    spalten = common.load_yaml("spalten.yaml")
    live = common.load_yaml("live_spalten.yaml")
    known = {(v if isinstance(v, str) else v["name"]) for v in spalten["spalten"].values()}
    known |= set(spalten["abgeleitet"]) | {s["name"] for s in live["stats"].values()}
    for pid, prof in CFG["profile"].items():
        assert prof["positionen"], pid
        for sp in prof["stats"]:
            assert sp["stat"] in known, f"{pid}: {sp['stat']} nicht gemappt"
            assert sp["art"] in ("p90", "pct", "direkt")
            a, o, g = sp["schlecht"], sp["ok"], sp["gut"]
            assert (a < o < g) or (a > o > g), f"{pid}/{sp['stat']}: Anker nicht geordnet"
    assert len(CFG["profile"]) == 12
