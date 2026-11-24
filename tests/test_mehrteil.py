"""Mehrteil-Suche: Teil-Exporte gleichen Datums -> ein Snapshot, Duplikate, Re-Import, Limit-Warnung."""

import importlib.util
from pathlib import Path

import common
import pandas as pd
import pytest
import stand

FIX = Path(__file__).parent / "fixtures" / "echt"
SUCHE = FIX / "2026-10-11_suche_stuermer.csv"

_spec = importlib.util.spec_from_file_location("fm_import", Path(common.ROOT) / "scripts" / "import.py")
fm_import = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm_import)

CFG = common.load_yaml("spalten.yaml")


def _df() -> pd.DataFrame:
    return fm_import.read_table(SUCHE)


def _write(df: pd.DataFrame, path: Path) -> Path:
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _imp(conn, path, **kw):
    warnings: list[str] = []
    res = fm_import.import_file(conn, "t", path, CFG, warn=warnings.append, log=lambda m: None, **kw)
    return res, warnings


def _players(conn) -> dict[str, int]:
    return dict(conn.execute("select player_uid, minutes from players").fetchall())


def test_dateinamen_konvention(tmp_path):
    for n in ("2027-07-14_suche_b.csv", "2027-07-14_suche.csv", "2027-07-14_suche_2.csv",
              "2027-07-14_kader.csv", "2027-07-15_suche.csv", "2027-07-14_suche_x.png"):  # fmt: skip
        (tmp_path / n).write_text("x")
    teile = fm_import.part_files(tmp_path / "2027-07-14_suche_2.csv")
    assert [p.name for p in teile] == [
        "2027-07-14_suche.csv", "2027-07-14_suche_2.csv", "2027-07-14_suche_b.csv"
    ]  # fmt: skip


def test_mehrteil_ein_snapshot(tmp_path):
    df = _df()
    _write(df.iloc[:2], tmp_path / "2026-10-11_suche.csv")
    _write(df.iloc[2:], tmp_path / "2026-10-11_suche_2.csv")
    c = common.connect(":memory:")
    res, _ = _imp(c, tmp_path / "2026-10-11_suche.csv")
    assert res["teile"] == 2 and res["rows"] == 4
    assert c.execute("select count(*) from snapshots").fetchone()[0] == 1
    assert c.execute("select source_file, rows from snapshot_files order by rowid").fetchall() == [
        ("2026-10-11_suche.csv", 2), ("2026-10-11_suche_2.csv", 2)
    ]  # fmt: skip
    assert len(_players(c)) == 4
    # stand.py kennt beide Teile als importiert
    assert stand.nicht_importiert(c, "t", tmp_path) == []


def test_duplikate_ueber_teile(tmp_path):
    df = _df()
    mcol = next(k for k, v in CFG["spalten"].items() if v == "minutes")
    b = df.iloc[[0, 1, 2]].copy()
    b.iloc[0, df.columns.get_loc(mcol)] = "4321"  # Spieler 0 abweichend, mehr Minuten
    _write(df.iloc[:2], tmp_path / "2026-10-11_suche.csv")
    _write(b, tmp_path / "2026-10-11_suche_liga2.csv")
    c = common.connect(":memory:")
    res, _ = _imp(c, tmp_path / "2026-10-11_suche_liga2.csv")
    assert (res["doppelt_gleich"], res["doppelt_abweichend"], res["rows"]) == (1, 1, 3)
    assert _players(c)[str(df.iloc[0]["Unique ID"])] == 4321


def test_reimport_teil_loescht_andere_nicht(tmp_path):
    df = _df()
    a = _write(df.iloc[:2], tmp_path / "2026-10-11_suche.csv")
    b = _write(df.iloc[2:], tmp_path / "2026-10-11_suche_2.csv")
    c = common.connect(":memory:")
    _imp(c, a)
    _imp(c, b)  # Re-Import nur von Teil 2
    assert len(_players(c)) == 4
    assert c.execute("select count(*) from snapshots").fetchone()[0] == 1
    assert c.execute("select count(*) from snapshot_files").fetchone()[0] == 2
    # Teil fehlt auf der Platte -> Abbruch statt stillem Löschen
    b.unlink()
    with pytest.raises(ValueError, match="fehlen"):
        _imp(c, a)
    assert len(_players(c)) == 4
    _, w = _imp(c, a, fehlende_teile_ok=True)
    assert len(_players(c)) == 2 and any("entfallen" in m for m in w)


def test_altbestand_getrennte_snapshots_werden_zusammengefuehrt(tmp_path):
    df = _df()
    c = common.connect(":memory:")
    for i, n in enumerate(("2026-10-11_suche_angreifer.csv", "2026-10-11_suche_stuermer.csv")):
        p = _write(df.iloc[i * 2 : i * 2 + 2], tmp_path / n)
        with c:  # Altimport: ein Snapshot je Datei, ohne snapshot_files
            sid = c.execute(
                "insert into snapshots(save, ingame_date, source_file, view_type, imported_at) "
                "values('t','2026-10-11',?,'suche','x')", (p.name,)
            ).lastrowid  # fmt: skip
            c.execute("insert into players(snapshot_id, player_uid) values(?, ?)", (sid, f"alt{i}"))
    _imp(c, tmp_path / "2026-10-11_suche_stuermer.csv")
    assert c.execute("select count(*) from snapshots").fetchone()[0] == 1
    assert len(_players(c)) == 4 and "alt0" not in _players(c)


def test_kader_bleibt_einzeldatei(tmp_path):
    k = FIX / "2026-10-11_kader.csv"
    c = common.connect(":memory:")
    res, _ = _imp(c, k)
    assert "teile" not in res
    assert c.execute("select source_file, rows from snapshot_files").fetchall() == [
        (k.name, res["rows"])
    ]


def test_limit_warnung_und_stand(tmp_path, monkeypatch):
    monkeypatch.setattr(fm_import, "LIMIT_WARN", 3)
    monkeypatch.setattr(stand, "LIMIT_WARN", 3)
    df = _df()
    _write(df.iloc[:3], tmp_path / "2026-10-11_suche.csv")
    _write(df.iloc[3:], tmp_path / "2026-10-11_suche_2.csv")
    c = common.connect(":memory:")
    _, w = _imp(c, tmp_path / "2026-10-11_suche.csv")
    limit = [m for m in w if "Exporter-Limit" in m]
    assert len(limit) == 1 and "2026-10-11_suche.csv: 3 Zeilen" in limit[0]
    t = stand.such_teile(c, "t")
    assert [(x["datei"], x["zeilen"], x["limit"]) for x in t["teile"]] == [
        ("2026-10-11_suche.csv", 3, True), ("2026-10-11_suche_2.csv", 1, False)
    ]  # fmt: skip
    assert not t["altimport"]


def test_stand_altimport_ohne_teilliste(tmp_path, monkeypatch):
    monkeypatch.setattr(stand, "LIMIT_WARN", 2)
    c = common.connect(":memory:")
    sid = c.execute(
        "insert into snapshots(save, ingame_date, source_file, view_type, imported_at) "
        "values('t','2027-07-14','2027-07-14_suche.csv','suche','x')"
    ).lastrowid
    for i in range(2):
        c.execute("insert into players(snapshot_id, player_uid) values(?, ?)", (sid, f"p{i}"))
    t = stand.such_teile(c, "t")
    assert t["altimport"] and t["teile"] == [
        {"datei": "2027-07-14_suche.csv", "zeilen": 2, "limit": True}
    ]
    assert stand.such_teile(common.connect(":memory:"), "t") is None
