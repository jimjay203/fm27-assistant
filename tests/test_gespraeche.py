"""Gesprächsvorschläge: Regeln, Schwellen, Abklingzeit, Moral-Hinweis, Speichern erledigter Gespräche."""

import datetime as dt

import common
import gespraeche as g
import pandas as pd
import pytest

CFG = g.config()
HEUTE = dt.date(2027, 10, 15)
DATEN = ["2027-09-01", "2027-09-08", "2027-09-15", "2027-09-22", "2027-10-09"]


def einsaetze(zeilen):
    """zeilen: (uid, datum, note, minuten, einwechslung)."""
    return pd.DataFrame(
        [{"player_uid": u, "datum": d, "eingesetzt": 1, "note": n, "minuten": m, "einwechslung": e}
         for u, d, n, m, e in zeilen]
    )  # fmt: skip


def reihe(uid, noten, minuten=None, letzte_ein=0):
    out = [(uid, d, n, minuten, 0) for d, n in zip(DATEN[-len(noten) :], noten, strict=True)]
    if letzte_ein:
        out[-1] = (*out[-1][:4], 1)
    return out


def run(zeilen, spieler, moral=None, erledigt=None, cfg=CFG):
    return g.vorschlaege(einsaetze(zeilen), spieler, moral or {}, erledigt or [], cfg, HEUTE,
                         {"2027-10-09": "Gladbach"})  # fmt: skip


def typen(res):
    return {v["uid"]: v["typ"] for v in res["vorschlaege"]}


def test_lob_leistung_vor_form_lob():
    res = run(reihe("1", [7.5, 7.4, 7.3, 7.6, 8.0]), {"1": "A"})
    v = res["vorschlaege"][0]
    assert v["typ"] == "lob_leistung" and "Gladbach" in v["grund"] and "8,0" in v["grund"]
    assert [w["typ"] for w in v["weitere"]] == ["lob_form"]
    assert res["letztes_spiel"] == {"datum": "2027-10-09", "gegner": "Gladbach"}


def test_form_lob_braucht_mindesteinsaetze():
    assert typen(run(reihe("1", [7.3, 7.3, 7.3]), {"1": "A"})) == {"1": "lob_form"}
    assert typen(run(reihe("1", [7.3, 7.3]), {"1": "A"})) == {}


def test_kritik_nur_mit_genug_minuten_oder_startelf():
    assert typen(run(reihe("1", [5.9], minuten=60), {"1": "A"})) == {"1": "kritik_leistung"}
    assert typen(run(reihe("1", [5.9], minuten=20), {"1": "A"})) == {}
    # Minuten unbekannt (manuell erfasst): nur Startelf
    assert typen(run(reihe("1", [5.9]), {"1": "A"})) == {"1": "kritik_leistung"}
    assert typen(run(reihe("1", [5.9], letzte_ein=1), {"1": "A"})) == {}


def test_kritik_form_und_moral_hinweis():
    res = run(reihe("1", [6.3, 6.2, 6.4, 6.5, 6.5]), {"1": "A"}, moral={"1": "Leicht unzufrieden"})
    v = res["vorschlaege"][0]
    assert v["typ"] == "kritik_form" and v["moral_niedrig"] and "ungeprüft" in v["hinweis"]
    live = run(reihe("1", [6.3, 6.2, 6.4]), {"1": "A"}, moral={"1": 25})
    assert live["vorschlaege"][0]["moral_niedrig"]


def test_nicht_im_letzten_spiel_kein_leistungsvorschlag():
    zeilen = [("1", "2027-09-22", 8.5, 90, 0), ("2", "2027-10-09", 6.8, 90, 0)]
    res = run(zeilen, {"1": "A", "2": "B"})
    assert typen(res) == {} and res["ohne"] == 2


def test_abklingzeit_sperrt_und_laeuft_ab():
    zeilen = reihe("1", [8.0])
    frisch = [{"datum": "2027-10-10", "uid": "1", "typ": "lob_leistung"}]
    res = run(zeilen, {"1": "A"}, erledigt=frisch)
    assert res["vorschlaege"] == [] and res["gesperrt"][0]["gesperrt_bis"] == "2027-10-24"
    alt = [{"datum": "2027-09-01", "uid": "1", "typ": "lob_form"}]
    assert typen(run(zeilen, {"1": "A"}, erledigt=alt)) == {"1": "lob_leistung"}


def test_nur_aktueller_kader_und_sortierung():
    zeilen = reihe("1", [5.5], minuten=90) + reihe("2", [8.0]) + reihe("3", [9.0])
    res = run(zeilen, {"1": "Z", "2": "A"})  # 3 nicht mehr im Kader
    assert [v["uid"] for v in res["vorschlaege"]] == ["2", "1"]


def test_ohne_einsaetze():
    res = g.vorschlaege(pd.DataFrame(), {"1": "A"}, {}, [], CFG, HEUTE)
    assert res["vorschlaege"] == [] and res["ohne"] == 1 and res["letztes_spiel"]["datum"] is None


def test_erledigt_speichern(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "save_dir", lambda save: tmp_path / save)
    g.erledigt_speichern("t", "12", "lob_form", "2027-10-15", "Ä Spieler")
    g.erledigt_speichern("t", "13", "kritik_form", "2027-10-16")
    alle = g.erledigt_laden("t")
    assert [(e["uid"], e["typ"]) for e in alle] == [("12", "lob_form"), ("13", "kritik_form")]
    assert alle[0]["name"] == "Ä Spieler"
    with pytest.raises(SystemExit):
        g.erledigt_speichern("t", "12", "unsinn", "2027-10-15")
    with pytest.raises(SystemExit):
        g.erledigt_speichern("t", "12", "lob_form", "15.10.2027")


def test_moral_live(monkeypatch):
    resp = {"date": "2027-10-15", "my_clubs": [{"uid": 9}], "rows": [
        {"UID": 1, "Name": "A", "Club ID": 9, "Morale": 70},
        {"UID": 2, "Name": "B", "Club ID": 5, "Loaned From ID": 9, "Morale": 40},  # verliehen: nicht im Kader
    ]}  # fmt: skip
    monkeypatch.setattr(g.live, "api_get", lambda url, pfad: resp)
    assert g.moral_live("x") == {"datum": "2027-10-15", "spieler": {"1": "A"}, "moral": {"1": 70}}
    monkeypatch.setattr(g.live, "api_get", lambda url, pfad: {"my_clubs": [], "rows": []})
    with pytest.raises(SystemExit):
        g.moral_live("x")
