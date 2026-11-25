"""SpielLogger-Analyse: nur Gespieltes, Tore mit Auslöser, Spielbericht aus Bildschirm-Export, Import in die DB."""

import json

import common
import pytest
import spielanalyse
import spielbericht
import spieldaten
import spielimport
import spielkennzahlen

TW_WIR, STUERMER, FLUEGEL, TW_GEG, IV_GEG = 1, 2, 3, 11, 12


def _spieler():
    daten = [
        (TW_WIR, 0, "Hein", 0), (STUERMER, 0, "Manneh", 1), (FLUEGEL, 0, "Arthur", 2),
        (TW_GEG, 1, "Atubolu", 3), (IV_GEG, 1, "Baum", 4),
    ]  # fmt: skip
    return [{"t": "spieler", "uid": u, "team": t, "name": n, "index": i, "art": "Player", "nr": i} for u, t, n, i in daten]


def _frame(ts, ball_z):
    pos = [[0, 0, 0, -50], [1, 0, 0, ball_z - 2], [2, 25, 0, ball_z], [3, 0, 0, 51], [4, 3, 0, ball_z - 4]]
    return {
        "t": "frame", "ts": ts, "min": 0, "sek": ts // 4, "periode": "FirstHalf", "modus": "Highlight", "aktiv": True,
        "ball": [0, 0, ball_z], "spieler": pos,
    }  # fmt: skip


def _ereignis(i, ts, name, *uids, seite="Home"):
    return {"t": "ereignis", "i": i, "ts": ts, "name": f"Event{name}", "spieler": list(uids), "team": seite, "data1": 15}


@pytest.fixture
def mitschnitt(tmp_path):
    zeilen = [
        {"t": "kopf", "spiel_id": 7},
        {"t": "setup", "info": {"competitionYear": "2027"}, "wetter": {"day": "311"}},
        *_spieler(),
        _ereignis(0, 4, "PassShortForward", IV_GEG, TW_GEG, seite="Away"),
        _ereignis(1, 8, "GoodIntercept", FLUEGEL),
        _ereignis(2, 20, "CrossLowFromRight", FLUEGEL, STUERMER),
        _ereignis(3, 24, "DefaultShot", STUERMER, TW_GEG),
        _ereignis(4, 24, "ShotMadeSure", STUERMER),
        _ereignis(5, 28, "GoalScored", STUERMER, FLUEGEL),
        _ereignis(6, 28, "GoalOne", STUERMER),
        _ereignis(7, 200, "GoalScored", IV_GEG, seite="Away"),  # vorausberechnet, noch nicht gespielt
        *[_frame(ts, z) for ts, z in ((4, -20), (8, -15), (12, -5), (16, 10), (20, 30), (24, 44), (28, 53))],
        {"t": "zaehler", "stufe": 4, "ereignisse": 8, "ts": 28, "gesehen": 28},
    ]
    pfad = tmp_path / "20260101_000000_7.jsonl"
    pfad.write_text("\n".join(json.dumps(z) for z in zeilen), encoding="utf-8")
    return pfad


def test_only_played_events_are_visible(mitschnitt):
    assert max(e.ts for e in spieldaten.laden(mitschnitt).ereignisse) == 28
    assert max(e.ts for e in spieldaten.laden(mitschnitt, alles=True).ereignisse) == 200


def test_goal_has_scorer_assist_trigger_and_distances(mitschnitt):
    spiel = spieldaten.laden(mitschnitt)
    (tor,) = spielanalyse.tore(spiel)
    assert (tor.team, tor.schuetze, tor.vorlage) == (0, STUERMER, FLUEGEL)
    assert tor.ausloeser == "Konter, Ballgewinn durch Arthur nach Kurzpass (~15 m) → Atubolu von Baum"
    assert [e.kat for e in tor.kette] == ["abfangen", "flanke", "schuss"]
    lage = spielanalyse.moment(spiel, 0, tor.abschluss.ts, STUERMER)
    assert lage["gegner"] == IV_GEG and lage["gegner_m"] == pytest.approx(3.6, abs=0.1)
    assert "Manneh (Vorlage Arthur)" in spielanalyse.beschreibung(spiel, tor, 1, wir=0)


def test_date_comes_from_setup():
    assert spieldaten.datum_aus_setup({"info": {"competitionYear": "2027"}, "wetter": {"day": "311"}}) == "2027-11-07"
    assert spieldaten.datum_aus_setup({"info": {"competitionYear": "2027"}, "wetter": {"day": "20"}}) == "2028-01-20"
    assert spieldaten.datum_aus_setup({}) is None


def _text(text, x, y, *pfad):
    return {"text": text, "x": x, "y": y, "b": 10, "h": 10, "pfad": list(pfad)}


def _bildschirm(pfad):
    texte = [
        _text("Werder Bremen", 10, 10, "Container", "HomeTeam", "ClubName"),
        _text("<style>Eintracht Frankfurt</style>", 900, 10, "Container", "AwayTeam", "ClubName"),
        _text("Sonntag, 7. November 2027", 400, 20, "MatchResult", "Datum"),
        _text("1 - 0", 500, 30, "MatchResult", "Container"),
        _text("Bundesliga", 500, 5, "MatchResult", "ClubText"),
    ]
    for key, (h, g) in {"Possession": ("42 %", "58 %"), "xG": ("3,05", "1,38"), "Shots": ("16", "11"),
                        "Corners": ("7", "4"), "Fouls": ("9", "11")}.items():  # fmt: skip
        texte += [_text(h, 100, 50, key, "bar", "Left-frame"), _text(g, 200, 50, key, "bar", "Right-frame")]
    for n, name in enumerate(("Hein", "Manneh", "Arthur")):
        x = 20 + 40 * n
        texte += [_text(name, x, 200, "AML", "Player", "Name"), _text("HRS", x, 185, "RatingBG", "PositionContainer")]
    texte.append(_text("Atubolu", 900, 200, "GK", "Player", "Name"))
    pfad.write_text(json.dumps({"texte": texte}), encoding="utf-8")


def test_result_screen_is_read_by_element_names(tmp_path):
    _bildschirm(tmp_path / "a.json")
    b = spielbericht.lesen(tmp_path / "a.json")
    assert (b["datum"], b["heim"], b["gast"]) == ("2027-11-07", "Werder Bremen", "Eintracht Frankfurt")
    assert b["werte"]["ballbesitz"] == ["42", "58"] and b["werte"]["tore"] == ["1", "0"]
    assert [p["spieler"] for p in b["aufstellung"][0]] == ["Hein", "Manneh", "Arthur"]
    assert b["aufstellung"][0][0]["rolle"] == "HRS"
    (tmp_path / "b.json").write_text('{"texte": []}', encoding="utf-8")
    assert spielbericht.lesen(tmp_path / "b.json") is None


def test_import_writes_events_kpis_and_replaces_on_rerun(mitschnitt, tmp_path):
    conn = common.connect(":memory:")
    conn.execute("INSERT INTO snapshots VALUES(1,'werder','2027-11-01','k.csv','kader','x')")
    for uid in (TW_WIR, STUERMER, FLUEGEL):
        conn.execute("INSERT INTO players(snapshot_id, player_uid, name) VALUES(1,?,'x')", (str(uid),))
    spiel = spieldaten.laden(mitschnitt)
    for _ in range(2):
        r = spielimport.importieren(conn, "werder", spiel, gegner="Frankfurt", archiv=tmp_path / "archiv")
    assert (r["datum"], r["wir"]) == ("2027-11-07", 0) and r["archiv"].exists()
    assert conn.execute("SELECT COUNT(*) FROM spiel_ereignisse").fetchone()[0] == 7
    kpis = dict(conn.execute("SELECT kpi, wert FROM spiel_spieler_kpis WHERE player_uid=?", (str(FLUEGEL),)))
    assert kpis == {"abfangen": 1, "flanken": 1, "flanken_angekommen": 1, "vorlagen": 1}
    assert len(spieldaten.laden(r["archiv"]).ereignisse) == 7


def test_shots_team_and_player_views(mitschnitt, tmp_path):
    spiel = spieldaten.laden(mitschnitt)
    ((szene, info),) = spielkennzahlen.szenen(spiel)
    assert (szene.schuetze, szene.vorlage, info["ausgang"]) == (STUERMER, FLUEGEL, "TOR")
    gewinne, verluste = spielkennzahlen.wechsel_des_ballbesitzes(spiel, 0)
    assert [e.uids[0] for e, _ in gewinne] == [FLUEGEL] and verluste == []
    assert [an for _, an in spielkennzahlen.paesse(spiel, 0)] == [STUERMER]
    text = spielkennzahlen.spieler_text(spiel, 0, "arthur", None, None)
    assert "Flanken angekommen | 1/1" in text
    assert "1:0" in spielkennzahlen.halbzeit_text(spiel, 0, None)
    pfade = spielanalyse.grafiken(spiel, szene, "Test", tmp_path / "tor_1", 0)
    assert [p.name for p in pfade] == ["tor_1_1.png", "tor_1_2.png"] and all(p.exists() for p in pfade)
