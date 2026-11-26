"""Gegen den Ball über mehrere Spiele: Reihen, Linienzahl, Zwischen-den-Linien, Gegenschuss-Herkunft, Laden."""

import json
import sqlite3

import gegenball as gb
import pytest
import spieldaten
import spielimport

# Werder (Team 0) greift nach +z an, Gegner (Team 1) nach -z. Gegner hat die ganze Zeit den Ball.
WIR = {  # uid: (x, z) – ohne Ball 4-2-3-1
    1: (0, -50),
    2: (-20, -20), 3: (-7, -20), 4: (7, -20), 5: (20, -20),
    6: (-5, -12), 7: (5, -12),
    8: (-18, -3), 9: (0, -3), 10: (18, -3),
    11: (0, 5),
}  # fmt: skip
GEGNER = {
    21: (0, 51),
    22: (-15, 30), 23: (0, 30), 24: (15, 30),  # Aufbaureihe 3
    25: (-20, 10), 26: (-5, 10), 27: (5, 10), 28: (20, 10),
    29: (0, -15),  # zentral zwischen unserer Kette (-20) und den Sechsern (-12)
    30: (-10, -18), 31: (10, -18),
}  # fmt: skip
SEKUNDEN = 400


def _zeilen():
    spieler = [
        {"t": "spieler", "uid": u, "team": team, "name": f"S{u}", "index": u, "art": "Player", "nr": u}
        for team, liste in ((0, WIR), (1, GEGNER)) for u in liste
    ]  # fmt: skip
    pos = [[u, x, 0, z] for liste in (WIR, GEGNER) for u, (x, z) in liste.items()]
    frames = [
        {"t": "frame", "ts": s * 4, "min": s // 60, "sek": s, "periode": "FirstHalf", "modus": "Highlight",
         "aktiv": True, "ball": [25, 0, -25], "spieler": pos}
        for s in range(SEKUNDEN)
    ]  # fmt: skip
    ereignisse, i = [], 0
    for ts in range(4, (SEKUNDEN - 20) * 4, 16):  # abwechselnd 23 -> 29 und 29 -> 23
        von, an = (23, 29) if (ts // 16) % 2 == 0 else (29, 23)
        ereignisse.append({"t": "ereignis", "i": i, "ts": ts, "name": "EventPassShortForward", "spieler": [von, an],
                           "team": "Away", "data1": 3})  # fmt: skip
        i += 1
    schuss_ts = (SEKUNDEN - 10) * 4
    ereignisse.append({"t": "ereignis", "i": i, "ts": schuss_ts, "name": "EventDefaultShot", "spieler": [30, 1],
                       "team": "Away", "data1": 3})  # fmt: skip
    return [
        {"t": "kopf", "spiel_id": 1},
        {"t": "setup", "info": {}},
        *spieler,
        *ereignisse,
        *frames,
    ]


@pytest.fixture
def spiel(tmp_path):
    pfad = tmp_path / "20270101_000000_1.jsonl"
    pfad.write_text("\n".join(json.dumps(z) for z in _zeilen()), encoding="utf-8")
    return spieldaten.laden(pfad, True)


def test_reihen_parse_and_split():
    assert gb.parse_reihen("4-2-3-1") == (4, 2, 3, 1)
    with pytest.raises(ValueError):
        gb.parse_reihen("4-4-1")
    pos = {u: (x, z, 500) for u, (x, z) in WIR.items() if u != 1}
    r = gb.reihen(pos, (4, 2, 3, 1))
    assert [round(x["laengs"]) for x in r] == [-20, -12, -3, 5]
    assert r[0]["breite"] == 40 and r[1]["breite"] == 10
    assert r[0]["spieler"] == [2, 3, 4, 5]  # links nach rechts


def test_linienzahl_and_sides():
    assert gb.linienzahl([-30, -30, -30, -10, 15, 18]) == 3
    assert gb.linienzahl([-30, -10, 15, 18], tiefste=False) == 2
    assert (
        gb.bahn(25) == "Flügel rechts"
        and gb.bahn(-10) == "Halbraum links"
        and gb.bahn(3) == "Mitte"
    )
    assert gb.ausloeser_art("Konter, Ballgewinn durch X") == "Konter"
    assert gb.ausloeser_art("Ecke (direkt)") == "Standard"
    assert gb.ausloeser_art("Ballgewinn durch X") == "Ballbesitz"
    assert gb.gegnertyp(3) == "Aufbau 3er" and gb.gegnertyp(4) == "Aufbau 4er+"


def test_auswerten_form_lines_and_shot_origin(spiel):
    w = gb.auswerten(spiel, 0, "2027-01-01", "Testgegner", (4, 2, 3, 1))
    assert round(w.abstand(0)) == 8 and round(w.abstand(1)) == 9 and round(w.abstand(2)) == 8
    assert round(w.form["linie"]) == round(-20 + 52.5)
    # Jeder zweite Pass kommt bei 29 an, der zentral zwischen Kette und Sechsern steht
    assert w.gegner_paesse > 0
    assert w.zwischen == pytest.approx(w.gegner_paesse / 2, abs=1)
    assert (w.aufbau, w.spitze, w.typ) == (3, 3, "Aufbau 3er")
    assert len(w.gegenschuesse) == 1
    assert w.gegenschuesse[0]["seite"] == "Flügel rechts"  # Ball bei x=25 aus unserer Sicht rechts
    text = gb.bericht([w], (4, 2, 3, 1))
    assert "Testgegner" in text and "Aufbau 3er" in text


def test_spiele_laden_skips_missing_files(spiel, tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.executescript(spielimport.SCHEMA)
    conn.executemany(
        "INSERT INTO spiel_logs(save, datum, gegner, datei, quelle, gesehen_ts, importiert_am) VALUES (?,?,?,?,?,?,?)",
        [("s", "2027-01-01", "Testgegner", "x", spiel.datei.name, 0, ""),
         ("s", "2027-01-08", "Fehlt FC", "x", "gibtsnicht.jsonl", 0, "")],
    )  # fmt: skip
    spiele, fehlend = gb.spiele_laden(conn, "s", None, None, tmp_path)
    assert [s[1] for s in spiele] == ["Testgegner"] and len(fehlend) == 1
    assert gb.spiele_laden(conn, "s", "2027-01-02", None, tmp_path)[0] == []
    assert gb.spiele_laden(conn, "s", None, "testgeg", tmp_path)[0][0][1] == "Testgegner"


def test_fluegelmomente_right_side(spiel):
    w = gb.auswerten(spiel, 0, "2027-01-01", "Testgegner", (4, 2, 3, 1))
    f = w.fluegel["rechts"]  # Ball steht bei x=25, z=-25: unsere Hälfte, rechts außen
    assert "links" not in w.fluegel and f["sekunden"] > 300
    assert f["om_hinter"] == 0  # Flügel rechts (18, -3) steht vor dem Ball
    assert round(f["om_vor_ball"]) == 22
    assert f["nah"] == 1  # nur der RV (20, -20) ist im Umkreis von 10 m
    assert "Flügelmomente" in gb.bericht([w], (4, 2, 3, 1))
