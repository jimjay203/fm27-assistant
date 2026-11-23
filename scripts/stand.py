"""Datenstand: was für Taktik-, Entwicklungs- und Transferfragen vorliegt, wie frisch es ist und was fehlt.

Schreibt nichts. Zeigt je Quelle das letzte In-Game-Datum und den Abstand zum neuesten Stand im Save, ob der
FMMT-27-Reader (live) erreichbar ist, nicht importierte Rohdateien, ob config/taktik_slots.yaml älter als
taktik.md ist, offene TODO-Felder in kontext.md und Einträge in log.md ohne Ergebnis.

Aufruf:  uv run python scripts/stand.py --save werder [--ohne-live]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402
import fmmt  # noqa: E402
import live  # noqa: E402
import spiele  # noqa: E402

IMPORT_EXT = {".csv", ".html", ".htm"}
VERALTET_TAGE = 30  # Quelle liegt so weit hinter dem neuesten Stand -> Hinweis


def _datum(s: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def snapshots(conn, save: str) -> list[dict]:
    """Je view_type: Anzahl Snapshots, letztes In-Game-Datum, Spieler bzw. Spiele im letzten Snapshot."""
    out = []
    for vt, n, letztes in conn.execute(
        "select view_type, count(*), max(ingame_date) from snapshots where save=? group by view_type", (save,)
    ):
        sid = conn.execute(
            "select max(id) from snapshots where save=? and view_type=? and ingame_date=?", (save, vt, letztes)
        ).fetchone()[0]
        zeilen = None if vt in common.TEAM_VIEWS else conn.execute(
            "select count(*) from players where snapshot_id=?", (sid,)
        ).fetchone()[0]
        out.append({"quelle": vt, "snapshots": n, "letztes": letztes, "zeilen": zeilen})
    return sorted(out, key=lambda r: common.VIEW_TYPES.index(r["quelle"]) if r["quelle"] in common.VIEW_TYPES else 99)


def team(conn, save: str) -> dict:
    n, letztes = conn.execute(
        "select count(*), max(ingame_date) from team_matches where save=?", (save,)
    ).fetchone()
    return {"quelle": "team_matches", "snapshots": n or 0, "letztes": letztes, "zeilen": n or 0}


def einsaetze(conn, save: str) -> dict:
    s = spiele.stand(conn, save)
    letztes = conn.execute("select max(datum) from spieleinsaetze where save=?", (save,)).fetchone()[0]
    return {"quelle": "spieleinsaetze", "snapshots": s["spiele"], "letztes": letztes, "zeilen": s["spieler"]}


def nicht_importiert(conn, save: str, raw_dir: Path) -> list[str]:
    if not raw_dir.is_dir():
        return []
    bekannt = {Path(r[0]).name for r in conn.execute("select source_file from snapshots where save=?", (save,))}
    return sorted(p.name for p in raw_dir.iterdir() if p.suffix.lower() in IMPORT_EXT and p.name not in bekannt)


def taktik_drift(taktik_md: Path, slots_yaml: Path) -> str | None:
    """Hinweis, wenn taktik.md nach config/taktik_slots.yaml geändert wurde (Rollen-Score rechnet mit der Kopie)."""
    if not taktik_md.exists() or not slots_yaml.exists():
        return None
    if taktik_md.stat().st_mtime > slots_yaml.stat().st_mtime + 60:
        return "taktik.md ist neuer als config/taktik_slots.yaml - Slots/Rollen prüfen und nachziehen"
    return None


def kontext_todos(kontext_md: Path) -> list[str]:
    """Felder der Kontext-Tabelle mit Wert TODO."""
    if not kontext_md.exists():
        return ["kontext.md fehlt"]
    out = []
    for zeile in kontext_md.read_text(encoding="utf-8").splitlines():
        teile = [t.strip() for t in zeile.strip().strip("|").split("|")]
        if zeile.startswith("|") and len(teile) >= 2 and teile[1].upper().startswith("TODO"):
            out.append(teile[0])
    return out


def log_offen(log_md: Path) -> list[dict]:
    """Log-Einträge (Tabellenzeilen mit Datum) ohne Ergebnis in der letzten Spalte."""
    if not log_md.exists():
        return []
    out = []
    for zeile in log_md.read_text(encoding="utf-8").splitlines():
        if not zeile.startswith("| 20"):
            continue
        teile = [t.strip() for t in zeile.strip().strip("|").split("|")]
        if len(teile) >= 6 and not teile[5] and teile[4] not in ("", "-"):
            out.append({"datum": teile[0], "bereich": teile[1], "pruefen": teile[4]})
    return out


def _kurz(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def ausgeben(save: str, quellen: list[dict], reader: dict | None, live_geprueft: bool, raw: list[str],
             drift: str | None, todos: list[str], offen: list[dict]) -> None:  # fmt: skip
    neuestes = max((d for q in quellen if (d := _datum(q["letztes"]))), default=None)
    print(f"Datenstand Save '{save}' (neuestes In-Game-Datum in der DB: {neuestes or '-'})\n")
    print(f"{'Quelle':<16}{'Anzahl':>8}{'letztes':>12}{'Tage zurück':>13}{'Zeilen':>9}")
    for q in quellen:
        d = _datum(q["letztes"])
        rueck = (neuestes - d).days if d and neuestes else None
        print(f"{q['quelle']:<16}{q['snapshots']:>8}{q['letztes'] or '-':>12}"
              f"{'' if rueck is None else rueck:>13}{'-' if q['zeilen'] is None else q['zeilen']:>9}")  # fmt: skip
    print("  Zeilen = Spieler im letzten Snapshot; team_matches = Spiele; spieleinsaetze = Spieler mit Spielliste")

    print("\nLive (FMMT-27):", end=" ")
    if not live_geprueft:
        print("nicht geprüft (--ohne-live)")
    elif reader is None:
        print("Reader nicht erreichbar -> DB-Stand nutzen und Datum nennen")
    elif not reader.get("ok"):
        print("Reader läuft, FM27 nicht lesbar -> DB-Stand nutzen und Datum nennen")
    else:
        print("bereit (exakte Marktwerte/Gehälter, Attribute eigener Spieler)")

    hinweise = [
        f"{q['quelle']} endet {q['letztes']}, {(neuestes - d).days} Tage vor dem neuesten Stand"
        for q in quellen
        if (d := _datum(q["letztes"])) and neuestes and (neuestes - d).days > VERALTET_TAGE
    ]
    if raw:
        hinweise.append(f"nicht importiert ({len(raw)}): {', '.join(raw)} -> scripts/import.py")
    if drift:
        hinweise.append(drift)
    if todos:
        hinweise.append(f"kontext.md TODO: {', '.join(todos)}")
    print("\nHinweise:" if hinweise else "\nHinweise: keine")
    for h in hinweise:
        print(f"  - {h}")

    print(f"\nlog.md ohne Ergebnis ({len(offen)}):" if offen else "\nlog.md: alle Einträge mit Ergebnis")
    for o in offen:
        print(f"  {o['datum']}  {o['bereich']:<12} prüfen: {_kurz(o['pruefen'])}")


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    common.add_common_args(ap)
    ap.add_argument("--url", default=live.DEFAULT_URL)
    ap.add_argument("--ohne-live", action="store_true", help="FMMT-Reader nicht abfragen")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    sdir = common.save_dir(save)
    cfg_dir = a.config_dir or common.ROOT / "config"
    conn = common.connect(a.db)
    quellen = snapshots(conn, save) + [team(conn, save), einsaetze(conn, save)]
    reader = None if a.ohne_live else fmmt.status(a.url)
    ausgeben(
        save, quellen, reader, not a.ohne_live, nicht_importiert(conn, save, sdir / "data" / "raw"),
        taktik_drift(sdir / "taktik.md", cfg_dir / "taktik_slots.yaml"),
        kontext_todos(sdir / "kontext.md"), log_offen(sdir / "log.md"),
    )  # fmt: skip


if __name__ == "__main__":
    main()
