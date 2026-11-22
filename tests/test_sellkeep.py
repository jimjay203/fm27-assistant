"""Sell/Keep-Kaskade: ein Fall je Regelzweig, Ability/Alters-Benchmark, Kader-Zuordnung."""

import common
import live
import numpy as np
import pandas as pd
import pytest
import sellkeep

CFG = common.load_yaml("rollen.yaml")
SK = CFG["sell_keep"]
BASE = {
    "age": 26, "minutes": 2000, "share": 0.9, "contract_end": "2029-06-30",
    "ingame_date": "2026-12-01", "vs_alter": np.nan, "value": 1e6, "fair_value": 1e6,
    "pos": "ST (C)",
}  # fmt: skip


def label(**kw):
    return sellkeep.classify(BASE | kw, SK)[0]


def test_young_low_minutes_by_age_benchmark():
    assert label(minutes=100, age=19, vs_alter=105) == "Entwickeln"
    assert label(minutes=100, age=19, vs_alter=90) == "Leihe prüfen"
    assert label(minutes=100, age=19, vs_alter=70) == "Abgeben prüfen"
    assert label(minutes=100, age=19) == "Zu wenig Daten"  # keine Attribute


def test_old_low_minutes_not_enough_data():
    assert label(minutes=100, age=28) == "Zu wenig Daten"


def test_expiring_contract():
    assert label(contract_end="2027-03-01", share=0.9) == "Verlängern prüfen"
    assert label(contract_end="2027-03-01", share=0.1) == "Jetzt verkaufen"
    assert label(contract_end="2027-12-02") == "Behalten"  # knapp über 12 Monate


def test_expensive_player():
    assert label(value=3e6, share=0.1) == "Teuer verkaufen"
    assert label(value=3e6, share=0.9, age=24) == "Behalten"  # Stammspieler, jung: nicht verkaufen
    assert label(value=3e6, share=0.9, age=28) == "Teuer verkaufen"  # peak-1 = 28
    assert (
        label(value=3e6, fair_value=np.nan, share=0.9) == "Behalten"
    )  # ohne Fair Value kein Urteil


def test_surplus_and_decline():
    assert label(share=0.1) == "Überzählig"
    assert label(share=0.4, age=30) == "Vor Abfall verkaufen"
    assert label(share=0.4, age=26) == "Behalten"


def test_goalkeeper_peaks_later():
    assert label(share=0.4, age=30, pos="GK") == "Behalten"
    assert label(share=0.4, age=33, pos="GK") == "Vor Abfall verkaufen"


def test_ability_and_vs_alter():
    attrs = {a: 14.0 for a in CFG["ability"]["archetypen"]["9"]}
    assert sellkeep.best_ability("ST (C)", attrs, CFG) == pytest.approx(14.0)
    assert np.isnan(sellkeep.best_ability("ST (C)", {}, CFG))  # keine Attribute
    assert np.isnan(sellkeep.best_ability("XX", attrs, CFG))  # unbekannte Position
    assert sellkeep.vs_alter(13.8, 24, CFG) == 100
    assert sellkeep.vs_alter(13.8, 30, CFG) == 100  # ab 24 geklemmt
    assert sellkeep.vs_alter(10.3, 12, CFG) == 100  # bis 15 geklemmt
    assert np.isnan(sellkeep.vs_alter(np.nan, 20, CFG))


def test_midfielder_takes_best_archetype():
    only_ten = {a: 18.0 for a in CFG["ability"]["archetypen"]["10"]}
    only_ten |= {a: 5.0 for a in CFG["ability"]["archetypen"]["WB/6"] if a not in only_ten}
    got = sellkeep.best_ability("M (C)", only_ten, CFG)
    assert got == pytest.approx(
        sellkeep.ability_score(only_ten, CFG["ability"]["archetypen"]["10"])
    )


def test_squad_status_from_live_flag_and_from_club_name():
    conn = common.connect(":memory:")
    cfg = common.load_yaml("live_spalten.yaml") | {"gehalt": {"periode": "woche", "faktor": 1.0}, "wert": {"faktor": 1.0}}
    mk = lambda uid, club_id, owner_id, club="X": {
        "UID": uid, "Name": str(uid), "Club": club, "Division": "L", "Position": "ST (C)",
        "Age": 25, "Mins": 900, "Wage": 1, "Transfer Value": "£1M", "Expires": "30/06/2029",
        "Team": "Senior Team", "Club ID": club_id, "Loaned From": "Werder" if owner_id else "",
        "Loaned From ID": owner_id,
    }  # fmt: skip
    resp = {
        "ok": True, "date": "2026-12-01", "my_clubs": [{"name": "W", "uid": 1}],
        "rows": [mk(1, 1, None), mk(2, 1, 7), mk(3, 9, 1), mk(4, 9, None)],
    }  # fmt: skip
    live.import_live(conn, "t", resp, cfg, lambda m: None)
    import per90

    players, _ = per90.load_wide(conn, "t")
    status = sellkeep.squad_status(players, conn, None).set_axis(players["player_uid"])
    assert status["1"] == "kader" and status["2"] == "leihe_ein" and status["3"] == "leihe_aus"
    assert pd.isna(status["4"])


def test_german_export_positions_are_normalized():
    import per90

    assert sellkeep.pos_tokens("V/FV (R), OM (Z), TW") == ["D", "WB", "AM", "GK"]
    assert per90.position_matches("V (Z), DM", ["D"]) and per90.position_matches("TW", ["GK"])
    assert not per90.position_matches("OM (Z)", ["D"])
    assert label(pos="TW", share=0.4, age=33) == "Vor Abfall verkaufen"  # TW -> GK, Peak 33
