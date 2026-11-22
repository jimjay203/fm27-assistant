"""vs_topclub: Topclub-Auswahl nach Kaderwert, Referenzverteilung und Prozent-Index."""

import benchmark as b
import numpy as np
import pandas as pd
import pytest

SP_UP = {"stat": "x", "art": "pct", "label": "x", "schlecht": 0, "ok": 5, "gut": 10}
SP_DOWN = {"stat": "g", "art": "pct", "label": "g", "schlecht": 10, "ok": 5, "gut": 0}


def players(club_values: dict[str, list[float]]) -> pd.DataFrame:
    rows = [
        {
            "club": c,
            "value": v,
            "team": "Senior Team",
            "minutes": 1500,
            "position": "ST (C)",
            "datenbasis": "voll",
        }
        for c, vs in club_values.items()
        for v in vs
    ]
    return pd.DataFrame(rows)


def test_topclubs_are_the_clubs_with_the_highest_summed_value_of_senior_players():
    df = players({"A": [10, 10], "B": [30], "C": [5], "D": [1]})
    df = pd.concat(
        [df, pd.DataFrame([{"club": "C", "value": 1000, "team": "Reserves"}])]
    )  # zählt nicht
    assert b.topclub_liste(df, 2) == ["B", "A"]
    assert b.topclub_liste(df, 10) == ["B", "A", "C", "D"]


def test_percent_in_reference_is_mid_rank_and_mirrors_for_lower_is_better():
    ref = np.arange(1.0, 11.0)  # 1..10
    assert b.prozent_im_referenz(ref, [5.5])[0] == pytest.approx(50)
    assert b.prozent_im_referenz(ref, [0.0, 99.0]).tolist() == [0, 100]
    assert b.prozent_im_referenz(ref, [5.0])[0] == pytest.approx(45)  # Gleichstand zählt halb
    assert b.prozent_im_referenz(ref, [0.0], niedriger_besser=True)[0] == 100
    assert np.isnan(b.prozent_im_referenz(ref, [np.nan])[0])


def test_reference_uses_only_topclub_senior_players_of_the_role_and_needs_enough_values():
    prof = {"positionen": [{"pos": "ST"}], "stats": [SP_UP, SP_DOWN]}
    df = players({"Top": [1] * 20, "Andere": [1] * 20})
    df["x"] = np.where(df["club"] == "Top", 8.0, 1.0)
    df["g"] = np.nan
    df.loc[df.index[:3], "g"] = 2.0  # nur 3 Werte < min_n
    ref = b.topclub_referenz(df, prof, {"min_minuten": 900}, ["Top"])
    assert set(ref) == {"x"} and len(ref["x"]) == 20 and (ref["x"] == 8.0).all()
    df.loc[df["club"] == "Top", "position"] = "D (C)"
    assert b.topclub_referenz(df, prof, {"min_minuten": 900}, ["Top"]) == {}


def test_vs_topclub_averages_over_stats_and_is_nan_without_reference():
    prof = {"stats": [SP_UP, SP_DOWN]}
    ref = {"x": np.arange(0.0, 10.0), "g": np.arange(0.0, 10.0)}
    sc = pd.DataFrame({"v_x": [9.5, 4.5, np.nan], "v_g": [0.5, 4.5, 4.5]})
    out = b.vs_topclub(sc, prof, ref)
    # x: 95 % / 50 %; g (niedriger besser): 100-5 = 95 % / 50 % -> Mittel 95 / 50
    assert out.iloc[0] == pytest.approx(95) and out.iloc[1] == pytest.approx(50)
    assert out.iloc[2] == pytest.approx(50)  # fehlende Statistik zählt nicht, g bleibt
    assert b.vs_topclub(sc, prof, {}).isna().all()
