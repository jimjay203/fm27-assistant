"""Saisonbasis der Per-90-Werte (per90.kombinieren / load_saison / mit_vorsaison, config/saison.yaml)."""

import benchmark as b
import common
import ligen
import numpy as np
import pandas as pd
import per90
import pytest

LG = ligen.Ligen.laden()
BL, BL2 = "Bundesliga (Deutschland)", "2. Bundesliga (Deutschland)"


def _df(rows):
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- Saisongrenze


def test_saison_grenze_ist_der_erste_juli():
    assert per90.saison_von("2027-06-30") == "2026/27"
    assert per90.saison_von("2027-07-01") == "2027/28"
    assert per90.saison_von("2027-05-31") == per90.vorsaison("2027/28") == "2026/27"
    assert per90.saison_von("1999-12-31") == "1999/00" and per90.saison_von(None) is None
    assert per90.saison_cfg()["uebergang"] == 1200  # Entscheidung Jimmy 07.07.2027


# --------------------------------------------------------------------------- Kombinieren


def test_gewicht_linear_minuten_zaehlwerte_und_raten():
    alt = _df([{"player_uid": "p", "club": "A", "league": "Bundesliga", "club_country": "Deutschland",
                "minutes": 2940, "tore": 10.0, "passquote_pct": 80.0}])  # fmt: skip
    neu = _df([{"player_uid": "p", "club": "A", "league": "Bundesliga", "club_country": "Deutschland",
                "minutes": 90, "tore": 1.0, "passquote_pct": 90.0, "value": 5e6}])  # fmt: skip
    r = per90.kombinieren(neu, alt, 1200).iloc[0]
    w = 1 - 90 / 1200
    assert r["w_vs"] == pytest.approx(w)
    assert r["minutes"] == pytest.approx(2940 * w + 90)
    assert r["tore"] == pytest.approx(10 * w + 1)  # Zählwert: VS x w + neu
    assert r["passquote_pct"] == pytest.approx(
        (80 * 2940 * w + 90 * 90) / (2940 * w + 90)
    )  # minutengewichtet
    assert r["minuten_text"] == "2940 (VS, w=0,93) + 90"
    assert r["value"] == 5e6 and r["min_neu"] == 90 and r["min_vs"] == 2940


def test_ab_uebergangsminuten_zaehlt_nur_die_neue_saison():
    alt = _df([{"player_uid": "p", "minutes": 3000, "tore": 30.0, "passquote_pct": 70.0}])
    neu = _df([{"player_uid": "p", "minutes": 1300, "tore": 2.0, "passquote_pct": 90.0}])
    r = per90.kombinieren(neu, alt, 1200).iloc[0]
    assert r["w_vs"] == 0 and r["minutes"] == 1300 and r["tore"] == 2 and r["passquote_pct"] == 90
    assert r["minuten_text"] == "3000 (VS, w=0,00) + 1300"


def test_neue_saison_ohne_minuten_ergibt_genau_die_vorsaison():
    alt = _df([{"player_uid": "p", "minutes": 1447, "tore": 3.0, "xg_pro_schuss_avg": 0.1234567,
                "team_possession": 55.5}])  # fmt: skip
    neu = _df([{"player_uid": "p", "minutes": 0, "tore": 0.0, "team_possession": 50.0}])
    r = per90.kombinieren(neu, alt, 1200).iloc[0]
    assert (r["minutes"], r["tore"], r["xg_pro_schuss_avg"], r["team_possession"]) == (
        1447,
        3,
        0.1234567,
        55.5,
    )


def test_vereinswechsel_neuester_verein_statistik_aus_beiden_saisons():
    alt = _df([{"player_uid": "p", "club": "Alt", "league": "2. Bundesliga", "club_country": "Deutschland",
                "minutes": 2000, "tore": 8.0, "value": 1e6}])  # fmt: skip
    neu = _df([{"player_uid": "p", "club": "Neu", "league": "Bundesliga", "club_country": "Deutschland",
                "minutes": 600, "tore": 1.0, "value": 9e6}])  # fmt: skip
    r = per90.kombinieren(neu, alt, 1200).iloc[0]
    assert (r["club"], r["value"], r["club_vs"], r["league_vs"]) == ("Neu", 9e6, "Alt", BL2)
    assert r["minutes"] == pytest.approx(2000 * 0.5 + 600) and r["tore"] == pytest.approx(
        8 * 0.5 + 1
    )
    # Statistik-Basis: Vorsaison überwiegt (1000 > 600) -> Verein/Liga der Vorsaison für Pool und Topclubs
    df = per90.kombinieren(neu, alt, 1200)
    assert b.statistik_liga(df, "club").iat[0] == "Alt" and b.statistik_liga(df).iat[0] == BL2


def test_spieler_nur_in_einer_saison():
    alt = _df([{"player_uid": "nur_vs", "minutes": 2500, "tore": 5.0},
               {"player_uid": "beide", "minutes": 1000, "tore": 2.0}])  # fmt: skip
    neu = _df([{"player_uid": "nur_neu", "minutes": 500, "tore": 1.0},
               {"player_uid": "beide", "minutes": 0, "tore": 0.0}])  # fmt: skip
    df = per90.kombinieren(neu, alt, 1200).set_index("player_uid")
    # fehlt in der neuen Suche (Minutenfilter des Exports) -> bleibt mit der Vorsaison
    assert df.loc["nur_vs", "minutes"] == 2500 and df.loc["nur_vs", "w_vs"] == 1
    assert df.loc["nur_neu", "minutes"] == 500 and pd.isna(df.loc["nur_neu", "min_vs"])
    assert df.loc["nur_neu", "minuten_text"] == "500"
    live = per90.kombinieren(neu, alt, 1200, nur_neu=True)
    assert set(live["player_uid"]) == {"nur_neu", "beide"}


def test_statistik_fehlt_in_einer_saison_rate_der_anderen():
    alt = _df([{"player_uid": "p", "minutes": 1800, "distanz_km": 180.0}])  # 9 km/90
    neu = _df([{"player_uid": "p", "minutes": 600}])  # Liga ohne Laufdaten
    r = per90.kombinieren(neu, alt, 1200).iloc[0]
    assert r["distanz_km"] / r["minutes"] * 90 == pytest.approx(9.0)


def test_ohne_vorsaison_bleibt_alles_unveraendert():
    neu = _df([{"player_uid": "p", "minutes": 900, "tore": 4.0, "passquote_pct": 81.0}])
    r = per90.kombinieren(neu, pd.DataFrame(columns=["player_uid"]), 1200).iloc[0]
    assert (r["minutes"], r["tore"], r["passquote_pct"], r["minuten_text"]) == (900, 4, 81, "900")
    assert pd.isna(r["w_vs"])


# --------------------------------------------------------------------------- Mindestminuten und Liga-Gewicht


def test_mindestminuten_gelten_auf_den_kombinierten_minuten():
    alt = _df([{"player_uid": u, "minutes": m, "tore": 1.0, "position": "ST (Z)"}
               for u, m in (("a", 1000), ("b", 1000), ("c", 0))])  # fmt: skip
    neu = _df([{"player_uid": u, "minutes": m, "tore": 1.0, "position": "ST (Z)"}
               for u, m in (("a", 500), ("b", 0), ("c", 500))])  # fmt: skip
    df = per90.kombinieren(neu, alt, 1200).set_index("player_uid")
    assert df.loc["a", "minutes"] == pytest.approx(1000 * (1 - 500 / 1200) + 500)  # 1083
    prof = {"positionen": [{"pos": "ST"}],
            "stats": [{"stat": "tore", "art": "p90", "schlecht": 0, "ok": 0.3, "gut": 0.6}]}  # fmt: skip
    drin = b.score_profile(df.reset_index(), prof, {"min_minuten": 900})["player_uid"]
    assert set(drin) == {"a", "b"}  # c: nur 500 neue Minuten


def test_liga_gewicht_je_saison_minutengewichtet():
    g1, g2 = LG.gewicht(BL, "standard"), LG.gewicht(BL2, "standard")
    assert g1 is not None and g2 is not None and g1 != g2
    w = LG.gewicht_saisons(BL, "standard", BL2, min_neu=300, min_vs_w=900)
    assert w == pytest.approx((g1 * 300 + g2 * 900) / 1200)
    assert LG.gewicht_saisons(BL, "standard", BL2, min_neu=300, min_vs_w=0) == g1
    assert LG.gewicht_saisons(BL, "standard") == g1
    df = pd.DataFrame({"league": [BL, BL], "league_vs": [BL2, None], "min_neu": [0.0, 500.0],
                       "min_vs_w": [2000.0, np.nan]})  # fmt: skip
    assert LG.gewicht_spalte(df, "standard").tolist() == pytest.approx([g2, g1])


# --------------------------------------------------------------------------- Laden aus der DB


def _db():
    conn = common.connect(":memory:")
    snaps = [(1, "2026-10-11", "suche"), (2, "2027-05-31", "kader"), (3, "2027-05-31", "suche"),
             (4, "2027-07-01", "kader")]  # fmt: skip
    for sid, d, v in snaps:
        conn.execute("INSERT INTO snapshots VALUES(?, 'w', ?, ?, ?, 'x')", (sid, d, f"f{sid}", v))
    spieler = [  # (snapshot, uid, club, minutes, value, tore)
        (1, "alt_suche", "X", 900, 1e6, 99.0),  # ältere Suche derselben Saison: veraltet
        (2, "eigen", "Werder Bremen", 2000, 2e6, 4.0),
        (2, "weg", "Werder Bremen", 1500, 1e6, 1.0),  # nicht mehr im neuen Kader
        (3, "kand", "Y", 2500, 3e6, 10.0),
        (3, "neu_eigen", "Z", 1800, 4e6, 6.0),  # im Sommer gekommen
        (4, "eigen", "Werder Bremen", 0, 2.5e6, 0.0),
        (4, "neu_eigen", "Werder Bremen", 0, 5e6, 0.0),
    ]
    for sid, uid, club, m, v, t in spieler:
        conn.execute(
            "INSERT INTO players(snapshot_id, player_uid, name, club, league, club_country, position, "
            "minutes, value) VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, uid, uid, club, "Bundesliga", "Deutschland", "ST (Z)", m, v),
        )
        conn.execute("INSERT INTO player_stats VALUES(?,?,'tore',?)", (sid, uid, t))
    return conn


def test_load_saison_letzter_snapshot_je_saison_und_quelle():
    df, _ = per90.load_saison(_db(), "w")
    info = df.attrs["saison"]
    assert info["aktuell"] == "2027/28" and info["vorsaison"] == "2026/27"
    assert info["neu"] == {"kader": (4, "2027-07-01")}
    assert info["vs"] == {"kader": (2, "2027-05-31"), "suche": (3, "2027-05-31")}
    d = df.set_index("player_uid")
    assert "alt_suche" not in d.index  # Suche vom Oktober ist durch die vom 31.05. ersetzt
    assert (d.loc["eigen", "value"], d.loc["eigen", "minutes"], d.loc["eigen", "tore"]) == (
        2.5e6,
        2000,
        4,
    )
    assert d.loc["eigen", "snapshot_id"] == 4  # Kernfelder vom neuesten Stand
    assert (d.loc["neu_eigen", "club"], d.loc["neu_eigen", "club_vs"]) == ("Werder Bremen", "Z")
    assert d.loc["kand", "minutes"] == 2500 and d.loc["weg", "minutes"] == 1500


def test_db_quelle_markiert_nur_den_neuen_kader_als_eigen():
    df = b.load_db(_db(), "w", eigene=True).set_index("uid")
    assert set(df.index[df["own"]]) == {"eigen", "neu_eigen"}
    assert df.loc["eigen", "eigen"] == "kader" and (df["team"] == "Senior Team").all()
    assert df.attrs["snapshots"] == {"kader": "2027-07-01", "suche": "2027-05-31"}


def test_live_mit_vorsaison_aus_der_db():
    live = pd.DataFrame({"uid": ["eigen", "kand", "neu"], "minutes": [270, 0, 90], "tore": [1.0, 0.0, 1.0],
                         "league": "Bundesliga", "own": [True, False, False]})  # fmt: skip
    live.attrs["date"] = "10.07.2027"
    df = per90.mit_vorsaison(_db(), "w", live, "2027-07-10").set_index("uid")
    assert df.attrs["saison"]["vorsaison"] == "2026/27" and df.attrs["date"] == "10.07.2027"
    w = 1 - 270 / 1200
    assert df.loc["eigen", "minutes"] == pytest.approx(2000 * w + 270)
    assert df.loc["eigen", "tore"] == pytest.approx(4 * w + 1)
    assert df.loc["kand", "minutes"] == 2500 and df.loc["neu", "minutes"] == 90
    assert "weg" not in df.index  # live fehlt nur, wer nicht mehr im Spiel ist
