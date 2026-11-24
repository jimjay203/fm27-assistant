"""Leihen: verliehene eigene Spieler zählen nicht als verfügbar, an uns geliehene schon; Leihende vorbei = zurück."""

import benchmark as b
import common
import ligen
import numpy as np
import pandas as pd
import planer
import sellkeep
from conftest import MINI_FORMATIONEN, mini_df, mini_rk

STICHTAG = "2027-07-17"
W = "Werder Bremen"


def _db(rows):
    """In-Memory-DB mit einem Kader-Snapshot; rows = (uid, club, loan_end, ausgeliehen_von)."""
    conn = common.connect(":memory:")
    conn.execute(
        "INSERT INTO snapshots(id, save, ingame_date, source_file, view_type, imported_at) "
        "VALUES (1, 't', ?, 'k.csv', 'kader', 'x')",
        (STICHTAG,),
    )
    for uid, club, ende, owner in rows:
        conn.execute(
            "INSERT INTO players(snapshot_id, player_uid, name, club, league, position, age, minutes, loan_end) "
            "VALUES (1, ?, ?, ?, 'Bundesliga', 'ST (Z)', 22, 1000, ?)",
            (uid, f"Spieler {uid}", club, ende),
        )
        if owner:
            conn.execute(
                "INSERT INTO player_info VALUES (1, ?, 'ausgeliehen_von', ?)", (uid, owner)
            )
    return conn


ROWS = [
    ("a", W, None, None),  # eigener Kader
    ("b", "Magdeburg", "2028-06-29", W),  # an Magdeburg verliehen
    ("c", W, "2028-06-30", "Ajax"),  # von Ajax geliehen
    ("d", "Laval", "2027-06-30", W),  # Leihe vorbei -> wieder bei uns
    ("e", W, "2027-06-30", "Freiburg"),  # Leihe an uns vorbei -> nicht mehr unser Spieler
    ("f", "Ajax", None, None),  # fremd
]


def _status(stichtag=STICHTAG, mit_datum=False):
    conn = _db(ROWS)
    players = pd.DataFrame(ROWS, columns=["player_uid", "club", "loan_end", "owner"]).assign(
        snapshot_id=1
    )
    if mit_datum:
        players["ingame_date"] = STICHTAG
    return sellkeep.squad_status(players, conn, W, stichtag).set_axis(players["player_uid"])


def test_verliehen_raus_geliehen_drin_leihende_vorbei():
    st = _status()
    assert st["a"] == "kader" and st["b"] == "leihe_aus" and st["c"] == "leihe_ein"
    assert st["d"] == "kader"  # Leihende in der Vergangenheit: wieder verfügbar
    assert pd.isna(st["e"]) and pd.isna(st["f"])
    assert sellkeep.verfuegbar(st).to_dict() == {
        "a": True, "b": False, "c": True, "d": True, "e": False, "f": False
    }  # fmt: skip


def test_stichtag_default_ist_das_in_game_datum_der_zeile():
    assert _status(stichtag=None, mit_datum=True)["d"] == "kader"
    # ohne Datum keine Annahme: Status bleibt wie im Export
    assert _status(stichtag=None)["d"] == "leihe_aus"


def test_leihe_text():
    assert sellkeep.leihe_text("leihe_aus", "2028-06-29") == "verliehen bis 29.06.2028"
    assert sellkeep.leihe_text("leihe_ein", "2028-06-30") == "Leihe bis 30.06.2028"
    assert sellkeep.leihe_text("leihe_aus", None) == "verliehen"
    assert sellkeep.leihe_text("kader", "2028-06-30") is None
    assert sellkeep.leihe_text(np.nan, None) is None


def test_benchmark_load_db_markiert_verliehene_nicht_als_kader():
    df = b.load_db(_db(ROWS), "t", eigene=True).set_index("uid")
    assert df.loc["a", "eigen"] == "kader" and df.loc["b", "eigen"] == "leihe_aus"
    assert df.loc["c", "eigen"] == "leihe_ein" and df.loc["d", "eigen"] == "kader"
    assert (
        not df.loc["e", "own"] and not df.loc["f", "own"]
    )  # f ist kein eigener Spieler (Club Ajax)


def _ctx_mit_leihen():
    df = mini_df()
    extra = pd.DataFrame({
        "uid": ["D", "E"], "name": ["Eigen D", "Eigen E"], "position": "ST (Z)", "minutes": 1500,
        "team": "Senior Team", "datenbasis": "voll", "league": "Bundesliga", "x": [99.0, 60.0],
        "f": [1.0, 40.0], "club": ["Magdeburg", "Wir"], "age": 21, "value": 5e6, "own": True,
        "eigen": ["leihe_aus", "leihe_ein"], "in_suche": False, "loan_end": ["2028-06-29", "2028-06-30"],
    })  # fmt: skip
    df = pd.concat([df, extra], ignore_index=True)
    return planer.kontext_bauen(
        df, mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900}, MINI_FORMATIONEN
    )


def test_plan_setzt_und_listet_verliehene_nicht_als_eigene():
    ctx = _ctx_mit_leihen()
    assert ctx.stand["n_eigene"] == 4 and ctx.stand["n_verliehen"] == 1  # A, B, C, E; D verliehen
    p = planer.plan(ctx, "2er", {}, planer.Filter())
    assert "D" not in p["elf"].values() and "E" in p["elf"].values()  # E (Leihe) ist verfügbar
    for sl in p["slots"].values():
        assert "D" not in {z["uid"] for z in sl["eigene"]}
        assert "D" not in {z["uid"] for z in sl["punkte"]["eigene"]}
        assert "D" not in {o["uid"] for o in sl["ohne_wertung"]}
        assert "D" not in {z["uid"] for z in sl["verbesserungen"]}  # auch kein Kandidat
        assert [(v["uid"], v["leihe"]) for v in sl["verliehen"]] == [
            ("D", "verliehen bis 29.06.2028")
        ]
        e = [z for z in sl["eigene"] if z["uid"] == "E"]
        assert e and e[0]["leihe"] == "Leihe bis 30.06.2028"


def test_suche_zeigt_verliehene_mit_hinweis():
    r = planer.suche(_ctx_mit_leihen(), "Mit", "Ohne", planer.Suche(text="eigen d"))
    assert [(z["uid"], z["leihe"]) for z in r["treffer"]] == [("D", "verliehen bis 29.06.2028")]


def test_eigener_snapshot_und_stichtag_aus_der_saisonbasis():
    p = pd.DataFrame()
    p.attrs["saison"] = {"neu": {"kader": (249, "2027-07-17"), "suche": (248, "2027-07-14")}}
    assert sellkeep.eigener_snapshot(p) == 249 and sellkeep.stichtag_aus(p) == "2027-07-17"
    p.attrs["saison"]["neu"]["live"] = (None, "2027-07-20")
    assert sellkeep.eigener_snapshot(p) == 249  # live ohne Snapshot-ID -> Kader
    p.attrs["saison"] = {}
    assert sellkeep.eigener_snapshot(p) is None and sellkeep.stichtag_aus(p) is None
