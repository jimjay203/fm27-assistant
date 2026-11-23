"""Spiellisten: Codes, Zuordnung Liste -> Spieler, Speichern, Auswertung je Position, Slot-Position."""

import common
import planer
import pytest
import spiele

C = spiele.codes()


def eintrag(datum, minuten=90, tore=0, vorlagen=0, note=7.0, bits=(1 << 1) | (1 << 19), rolle=45):
    return {"date": datum, "opponent": 761, "competition": 16, "played": minuten > 0, "position_bits": bits,
            "role": rolle, "xg": 0.1, "goals": tore, "assists": vorlagen, "sub_on": 0, "sub_off": 0,
            "minutes": minuten, "rating": note, "raw": "00"}  # fmt: skip


def db_mit_kader(tmp_path):
    """Zwei Kader-Exporte (01.01. und 01.02.2027) mit drei Spielern; B und C haben dieselben Minuten-Deltas."""
    conn = common.connect(tmp_path / "t.sqlite")
    werte = {  # uid: (name, position, (min, tore, vor, note) am 01.01., (...) am 01.02.)
        "A": ("Spieler A", "OM (R)", (500, 1, 0, 6.8), (680, 2, 1, 6.9)),
        "B": ("Spieler B", "D (C)", (900, 0, 0, 6.9), (1080, 0, 0, 7.0)),
        "C": ("Spieler C", "DM", (900, 0, 0, 6.6), (1080, 0, 0, 6.6)),
    }
    for i, d in enumerate(("2027-01-01", "2027-02-01")):
        sid = conn.execute(
            "insert into snapshots(save, ingame_date, source_file, view_type, imported_at) values(?,?,?,?,?)",
            ("t", d, f"{d}_kader.csv", "kader", "x"),
        ).lastrowid
        for uid, (name, pos, *st) in werte.items():
            m, t, v, n = st[i]
            conn.execute(
                "insert into players(snapshot_id, player_uid, name, position, minutes) values(?,?,?,?,?)",
                (sid, uid, name, pos, m),
            )
            for stat, val in (("tore", t), ("assists", v), ("wertung_avg", n)):
                conn.execute("insert into player_stats values(?,?,?,?)", (sid, uid, stat, val))
    conn.commit()
    return conn


def test_codes_und_labels():
    assert spiele.position_label((1 << 1) | (1 << 19), C) == "OM (R)"
    assert (
        spiele.position_label((1 << 1) | (1 << 30), C) == "Position #30"
    )  # unbekannt: nicht raten
    assert (
        spiele.rolle_label(45, C) == "Außenstürmer" and spiele.rolle_label(45, C, kurz=True) == "AS"
    )
    assert spiele.rolle_label(99, C) == "Rolle #99"
    rk = common.load_yaml("rollen_kpis.yaml")
    for r in C["rollen"].values():  # deutsche Namen gibt es im Rollenkatalog (oder als FM27-Alias)
        assert r["name"] is None or r["name"] in rk["rollen"] or r["name"] in rk.get("alias_rollen", {})
    assert spiele.rolle_label(39, C) == "Regista"  # ohne deutschen Namen: Enum-Name des Spiels
    assert spiele.position_label((1 << 1) | (1 << 22), C) == "ST (Z)"
    # Seitenbits zählen nicht als Position: IV halbrechts ist "V (Z)"
    assert spiele.position_label((1 << 1) | (1 << 12) | (1 << 28), C) == "V (Z)"
    assert spiele.position_label((1 << 1) | (1 << 15) | (1 << 29), C) == "DM"


def test_passt_position():
    assert spiele.passt_position("OM (R)", "M (R), OM (RL)")
    assert not spiele.passt_position("OM (R)", "OM (L)")
    assert spiele.passt_position("DM", "DM, M (Z)")
    assert spiele.passt_position("V (R)", "V/FV (R)")
    assert not spiele.passt_position("Position #12", "V (Z)")


def test_zuordnung_eindeutig_und_mehrdeutig(tmp_path):
    conn = db_mit_kader(tmp_path)
    staende = spiele.kader_staende(conn, "t")
    # A: 2 Spiele im Januar = 180 Min., 1 Tor, 1 Vorlage
    a = {
        "entries": [
            eintrag("2026-12-20"),
            eintrag("2027-01-10", 90, 1, 0),
            eintrag("2027-01-20", 90, 0, 1),
        ]
    }
    z = spiele.zuordnen(a, staende)
    assert z["uid"] == "A" and z["name"] == "Spieler A"
    # 180 Min., keine Tore: passt auf B und C; die Position (DM) entscheidet für C
    dm = (1 << 1) | (1 << 15)
    c = {"entries": [eintrag("2026-12-20", bits=dm), eintrag("2027-01-10", bits=dm, note=6.6),
                     eintrag("2027-01-20", bits=dm, note=6.6)]}  # fmt: skip
    z = spiele.zuordnen(c, staende)
    assert z["uid"] == "C" and z["grund"].startswith("Position")
    # Liste beginnt erst nach dem ersten Export: kein vollständiger Zeitraum, keine Zuordnung
    spaet = {"entries": [eintrag("2027-01-10")]}
    assert spiele.zuordnen(spaet, staende)["uid"] is None
    # nur Spiele ohne Einsatz
    leer = {"entries": [eintrag("2026-12-20", minuten=0)]}
    assert spiele.zuordnen(leer, staende)["grund"] == "keine Einsätze in der Liste"


def test_erfassen_speichern_und_je_position(tmp_path):
    conn = db_mit_kader(tmp_path)
    alt = {
        "entries": [
            eintrag("2026-12-20"),
            eintrag("2027-01-10", 90, 1, 0),
            eintrag("2027-01-20", 90, 0, 1),
        ]
    }
    rv = (1 << 1) | (1 << 10)
    neu = {"entries": [eintrag("2026-12-20"), eintrag("2027-01-10", 90, 1, 0), eintrag("2027-01-20", 90, 0, 1),
                       eintrag("2027-02-10", 30, bits=rv, rolle=2, note=None)]}  # fmt: skip
    res = spiele.erfassen(conn, "t", [alt, neu])
    assert [g["name"] for g in res["gespeichert"]] == [
        "Spieler A"
    ]  # beide Listen = A, die jüngere gilt
    df = spiele.einsaetze(conn, "t", "A")
    assert len(df) == 4 and set(df["position"]) == {"OM (R)", "V (R)"}
    je = {r["position"]: r for r in spiele.je_position(df)}
    assert (
        je["OM (R)"]["minuten"] == 270 and je["OM (R)"]["tore"] == 1 and je["OM (R)"]["note"] == 7.0
    )
    assert (
        je["V (R)"]["minuten"] == 30
        and je["V (R)"]["note"] is None
        and je["V (R)"]["rolle"] == "Außenverteidiger"
    )
    assert spiele.stand(conn, "t")["spieler"] == 1
    spiele.erfassen(conn, "t", [neu])  # erneut: keine Dubletten
    assert spiele.stand(conn, "t")["spiele"] == 4


@pytest.mark.parametrize(
    ("slot", "erwartet"),
    [({"position": "FL", "x": 85, "y": 32}, "OM (R)"), ({"position": "FL", "x": 12, "y": 42}, "M (L)"),
     ({"position": "AV", "x": 88, "y": 72}, "V (R)"), ({"position": "IV", "x": 63, "y": 78}, "V (Z)"),
     ({"position": "DM", "x": 62, "y": 56}, "DM"), ({"position": "TW", "x": 50, "y": 92}, "TW")],
)  # fmt: skip
def test_fm_position_des_slots(slot, erwartet):
    assert planer.fm_position(slot) == erwartet
