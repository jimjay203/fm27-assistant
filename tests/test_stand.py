"""Datenstand: Snapshots je Typ, nicht importierte Dateien, Taktik-Drift, kontext-TODOs, offene Log-Einträge."""

import os

import common
import stand


def _db(tmp_path):
    conn = common.connect(tmp_path / "t.sqlite")
    for d, datei, vt in (
        ("2027-01-01", "2027-01-01_kader.csv", "kader"),
        ("2027-03-01", "2027-03-01_kader.csv", "kader"),
        ("2027-01-05", "2027-01-05_spiel_x.csv", "spiel"),
    ):
        sid = conn.execute(
            "insert into snapshots(save, ingame_date, source_file, view_type, imported_at) values('t',?,?,?,'x')",
            (d, datei, vt),
        ).lastrowid
        if vt == "kader":
            n = 2 if d.startswith("2027-03") else 1
            for i in range(n):
                conn.execute("insert into players(snapshot_id, player_uid) values(?,?)", (sid, f"p{i}"))
    conn.commit()
    return conn


def test_snapshots_letzter_stand(tmp_path):
    q = {r["quelle"]: r for r in stand.snapshots(_db(tmp_path), "t")}
    assert q["kader"] == {"quelle": "kader", "snapshots": 2, "letztes": "2027-03-01", "zeilen": 2}
    assert q["spiel"]["zeilen"] is None
    assert stand.team(_db(tmp_path / "b"), "t")["snapshots"] == 0


def test_nicht_importiert(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("2027-01-01_kader.csv", "2027-04-01_kader.csv", "bild.png"):
        (raw / name).write_text("x")
    assert stand.nicht_importiert(_db(tmp_path), "t", raw) == ["2027-04-01_kader.csv"]


def test_taktik_drift(tmp_path):
    md, yml = tmp_path / "taktik.md", tmp_path / "slots.yaml"
    md.write_text("x")
    yml.write_text("x")
    os.utime(yml, (1000, 1000))
    os.utime(md, (5000, 5000))
    assert stand.taktik_drift(md, yml)
    os.utime(yml, (9000, 9000))
    assert stand.taktik_drift(md, yml) is None


def test_kontext_und_log(tmp_path):
    k = tmp_path / "kontext.md"
    k.write_text("| Feld | Wert |\n|---|---|\n| Verein | TODO |\n| Budget | 24 Mio. |\n", encoding="utf-8")
    assert stand.kontext_todos(k) == ["Verein"]
    log = tmp_path / "log.md"
    log.write_text(
        "| Datum | Bereich | Entscheidung | Kriterium | Prüfen am | Ergebnis |\n|---|---|---|---|---|---|\n"
        "| 2027-01-01 | Taktik | a | b | nach 3 Spielen |  |\n"
        "| 2027-01-02 | Taktik | a | b | nach 3 Spielen | erledigt |\n"
        "| 2027-01-03 | Hinweis | a | - | - |  |\n",
        encoding="utf-8",
    )
    assert [o["datum"] for o in stand.log_offen(log)] == ["2027-01-01"]
