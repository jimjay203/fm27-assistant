"""Prüfbericht zu SpielLogger-Mitschnitten (spiellog.py)."""

import json
import sqlite3

import spiellog


def _frame(ts, sek, hoehe, aktiv=True):
    return {
        "t": "frame", "ts": ts, "zeit": float(sek), "min": 0, "sek": sek, "periode": "FirstHalf", "aktiv": aktiv,
        "ball": [0.0, hoehe, 0.0] if aktiv else None, "spieler": [],
    }


def test_report_answers_the_four_questions(tmp_path):
    zeilen = [
        {"t": "kopf", "spiel_id": 7, "stufe": 4},
        {"t": "zaehler", "stufe": 4, "ereignisse": 2},
        {"t": "spieler", "uid": 11},
        {"t": "ereignis", "i": 0, "name": "EventPassShortForward", "ts": 100, "spieler": [11, 99, 0]},
        {"t": "ereignis", "i": 1, "name": "EventFoulTrip", "ts": 150, "spieler": [77]},  # wird neu berechnet
        {"t": "ereignis", "i": 1, "name": "EventShotWide", "ts": 180, "spieler": [11]},
        _frame(100, 1, 0.1),
        _frame(120, 2, 2.5),
        _frame(140, 3, 0.0, aktiv=False),
        {"t": "ball_spur", "von": 119, "punkte": [[0.0, 0.0, 0.0], [3.0, 2.5, 4.0]]},
        {"t": "ende", "grund": "controller weg"},
    ]
    datei = tmp_path / "spiel.jsonl"
    datei.write_text("\n".join(json.dumps(z) for z in zeilen) + '\n{"t": "frame", "ts"', encoding="utf-8")
    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE players(player_uid TEXT, name TEXT)")
    con.execute("INSERT INTO players VALUES ('11', 'Testspieler')")
    con.commit()
    con.close()

    e = spiellog.auswerten(spiellog.lesen(datei), db)

    assert (e["ereignisse"], e["ueberholt"]) == (2, 1)
    assert e["messabstand_median_s"] == 1 and e["luecken_ueber_5s"] == (0, 0)
    assert e["gruppen"]["Pass"] == 1 and e["gruppen"]["Shot"] == 1
    assert e["ts_je_sekunde"] == 20 and e["groesste_luecke_s"] == 4
    assert (e["frames"], e["frames_aktiv"]) == (3, 2)
    assert (e["uids_ereignisse"], e["uids_in_db"], e["uids_im_spieltagskader"]) == (2, 1, 1)
    assert e["ballhoehe"] == (0.1, 2.5)
    assert e["rueck_abstand_median"] == 5.0
    assert e["zeilen"]["defekt"] == 1
    assert "Testspieler" in spiellog.bericht(e)
