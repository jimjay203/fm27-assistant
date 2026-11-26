"""Entwicklungsseite: Attribut-Verlauf (Export + Live), Zeiträume aus kumulierten Saisonwerten, Saisonvergleich."""

import json
from types import SimpleNamespace

import common
import entwicklung as ew
import live
import pandas as pd
import pytest
import spiele

ABLEIT = {"passquote_pct": ["paesse_angekommen", "paesse_versucht"]}


def _snapshot(conn, sid, datum, spieler):
    """spieler: {uid: (name, minuten, {stat: wert}, {attribut: wert})}"""
    conn.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?)", (sid, "t", datum, f"{datum}_kader.csv", "kader", "x"))
    for uid, (name, mins, stats, attrs) in spieler.items():
        conn.execute(
            "INSERT INTO players(snapshot_id, player_uid, name, club, position, age, minutes) VALUES(?,?,?,?,?,?,?)",
            (sid, uid, name, "Wir", "IV (Z)", 22, mins),
        )
        for st, v in stats.items():
            conn.execute("INSERT INTO player_stats VALUES(?,?,?,?)", (sid, uid, st, v))
        for a, v in attrs.items():
            conn.execute("INSERT INTO player_attributes VALUES(?,?,?,?,?,?,?)", (sid, uid, a, v, 0, v, v))


@pytest.fixture
def db(tmp_path):
    conn = common.connect(tmp_path / "t.sqlite")
    # Saison 2026/27: zwei Exporte; Saison 2027/28: Reset auf 0, dann zwei Exporte
    _snapshot(conn, 1, "2027-02-01", {"A": ("Max Muster", 900, {"tore": 2, "paesse_angekommen": 400,
              "paesse_versucht": 500, "einsaetze_start_n": 10}, {"Passen": 12, "Tackling": 10, "Reflexe": 3})})
    _snapshot(conn, 2, "2027-05-31", {"A": ("Max Muster", 1800, {"tore": 5, "paesse_angekommen": 850,
              "paesse_versucht": 1000, "einsaetze_start_n": 20}, {"Passen": 13, "Tackling": 10, "Reflexe": 3})})
    _snapshot(conn, 3, "2027-07-01", {"A": ("Max Muster", 0, {"tore": 0, "paesse_angekommen": 0,
              "paesse_versucht": 0, "einsaetze_start_n": 0}, {"Passen": 13, "Tackling": 11, "Reflexe": 3})})
    _snapshot(conn, 4, "2027-09-01", {"A": ("Max Muster", 100, {"tore": 1, "paesse_angekommen": 40,
              "paesse_versucht": 50, "einsaetze_start_n": 1}, {"Passen": 13, "Tackling": 11, "Reflexe": 4})})
    _snapshot(conn, 5, "2027-10-01", {"A": ("Max Muster", 900, {"tore": 3, "paesse_angekommen": 440,
              "paesse_versucht": 500, "einsaetze_start_n": 10}, {"Passen": 14, "Tackling": 11, "Reflexe": 4})})
    conn.commit()
    yield conn
    conn.close()


def _ctx(save="t"):
    df = pd.DataFrame([{"uid": "A", "name": "Max Muster", "age": 22, "position": "IV (Z)", "own": True,
                        "eigen": "kader"}])  # fmt: skip
    ra = {"rollen": {"Innenverteidiger|mit": {"key": ["Tackling"]}, "Absichernder IV|ohne": {"key": ["Passen"]}}}
    slots = {"IV r": {"mit": "Innenverteidiger", "ohne": "Absichernder IV", "stamm": ["Muster"]}}
    return SimpleNamespace(df=df, save=save, ra=ra, rk={}, slots_taktik=slots, attr_schwelle=12, attr_stufe=None)


def test_live_stand_ergaenzt_export_und_export_gewinnt_am_selben_tag(db):
    live.attribute_mitschreiben(db, "t", {"A": {"Passen": 15, "Tackling": 11}}, "2027-11-15")
    live.attribute_mitschreiben(db, "t", {"A": {"Passen": 16, "Tackling": 11}}, "2027-11-15")  # gleicher Tag
    live.attribute_mitschreiben(db, "t", {"A": {"Passen": 1}}, "2027-10-01")  # Tag mit Export
    v = ew.attribut_verlauf(db, "t", ["A"])
    passen = v[v["attribute"] == "Passen"].set_index("datum")["value"]
    assert passen["2027-11-15"] == 16  # ein Stand je Tag, der letzte gilt
    assert passen["2027-10-01"] == 14  # Export vor Live
    tage = ew.stichtage(v)
    assert tage[-1] == {"datum": "2027-11-15", "quelle": "live"}
    assert {"datum": "2027-10-01", "quelle": "export"} in tage


def test_uebersicht_delta_key_minuten(db):
    u = ew.uebersicht(_ctx(), db, "2027-05-31", "2027-10-01")
    z = u["spieler"][0]
    assert z["slot"] == "IV r"
    assert z["delta"] == 2  # Passen +1, Tackling +1; Reflexe (Torwart) zählt beim Feldspieler nicht
    assert z["delta_key"] == 2 and z["n_key"] == 2
    assert z["minuten"] == 900  # neue Saison startet bei 0, nichts aus der alten nach dem 31.05.
    assert {p["attribut"] for p in z["plus"]} == {"Passen", "Tackling"}
    # Anfang mitten in der Saison: nur Minuten danach
    z2 = ew.uebersicht(_ctx(), db, "2027-02-01", "2027-10-01")["spieler"][0]
    assert z2["minuten"] == 900 + 900


def test_perioden_aus_kumulierten_werten_mit_saisonreset_und_zusammenlegen():
    ks = pd.DataFrame([
        {"datum": "2027-09-01", "saison": "2027/28", "minutes": 100, "tore": 1, "paesse_angekommen": 40, "paesse_versucht": 50},
        {"datum": "2027-10-01", "saison": "2027/28", "minutes": 900, "tore": 3, "paesse_angekommen": 440, "paesse_versucht": 500},
        {"datum": "2027-10-15", "saison": "2027/28", "minutes": 990, "tore": 4, "paesse_angekommen": 480, "paesse_versucht": 560},
    ])  # fmt: skip
    p = ew.perioden(ks, ["tore", "passquote_pct"], ABLEIT)
    # 100 Min. < 270: mit dem nächsten Zeitraum zusammengelegt; der letzte bleibt auch kurz stehen
    assert [(x["von"], x["bis"], x["minuten"]) for x in p] == [
        ("2027-07-01", "2027-10-01", 900), ("2027-10-01", "2027-10-15", 90)
    ]
    assert p[0]["werte"]["tore"] == pytest.approx(3 / 900 * 90)
    assert p[1]["werte"]["tore"] == pytest.approx(1 / 90 * 90)
    assert p[1]["werte"]["passquote_pct"] == pytest.approx(40 / 60 * 100)  # Quote aus Δ Zähler / Δ Nenner


def test_raten_gewichtet():
    vorher = pd.Series({"minutes": 900, "wertung_avg": 7.0, "einsaetze_start_n": 10, "sprints_p90": 10.0})
    nachher = pd.Series({"minutes": 1800, "wertung_avg": 7.2, "einsaetze_start_n": 20, "sprints_p90": 12.0})
    w = ew.zeitraum_werte(vorher, nachher, ["wertung_avg", "sprints_p90"], {})
    assert w["wertung_avg"] == pytest.approx(7.4)  # je Spiel: (7,2*20 - 7,0*10) / 10
    assert w["sprints_p90"] == pytest.approx(14.0)  # je Minute


def test_spieler_detail_json_mit_saisonvergleich_und_noten(db):
    spiele.speichern(db, "t", "A", {"entries": [
        {"date": "2027-09-10", "opponent": 1, "competition": 1, "played": True, "minutes": 90, "rating": 7.0,
         "goals": 0, "assists": 0, "xg": 0.0, "sub_on": 0, "sub_off": 0, "raw": "00"},
        {"date": "2027-09-17", "opponent": 2, "competition": 1, "played": True, "minutes": 90, "rating": 8.0,
         "goals": 1, "assists": 0, "xg": 0.4, "sub_on": 0, "sub_off": 0, "raw": "00"},
    ]})  # fmt: skip
    d = ew.spieler(_ctx(), db, "A", "2027-05-31", "2027-10-01")
    json.dumps(d, allow_nan=False)
    assert d["key"] == ["Tackling", "Passen"]
    assert d["zeitraum"] == {"start": "2027-05-31", "ende": "2027-10-01"}
    gruppen = {g["gruppe"] for g in d["attribute"]}
    assert "Torwart" not in gruppen
    passen = next(a for g in d["attribute"] for a in g["attribute"] if a["name"] == "Passen")
    assert passen["delta"] == 1 and passen["verlauf"][0] == ["2027-02-01", 12]
    assert d["saisonvergleich"]["vs"]["saison"] == "2026/27" and d["saisonvergleich"]["neu"]["minuten"] == 900
    tore = next(s for s in d["statistiken"] if s["stat"] == "tore")
    assert tore["vs"] == pytest.approx(5 / 1800 * 90, abs=0.01) and tore["neu"] == pytest.approx(0.3)
    assert [n["gleitend"] for n in d["noten"]] == [7.0, 7.5]


def test_fremder_spieler_wird_abgelehnt(db):
    with pytest.raises(SystemExit):
        ew.spieler(_ctx(), db, "X")


def test_team_nur_live_und_ohne_angabe_benannt():
    live_ctx = SimpleNamespace(stand={"quelle": "live"})
    assert ew.team_von(live_ctx, {"team": "Senior Team", "eigen": "kader"}) == "Profis"
    assert ew.team_von(live_ctx, {"team": "U19", "eigen": "kader"}) == "U19"
    assert ew.team_von(live_ctx, {"team": "unbekannt", "eigen": "kader"}) == "ohne Teamangabe"
    benannt = SimpleNamespace(stand={"quelle": "live"}, team_ohne_liste="Werder II")
    assert ew.team_von(benannt, {"team": "unbekannt", "eigen": "kader"}) == "Werder II"
    assert ew.team_von(live_ctx, {"team": "Senior Team", "eigen": "leihe_aus"}) == "verliehen"
    # Exporte: kein Team-Feld (daten_db setzt nur einen Platzhalter) -> keine Angabe
    assert ew.team_von(SimpleNamespace(stand={"quelle": "db"}), {"team": "Senior Team"}) is None
