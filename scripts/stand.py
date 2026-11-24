"""Datenstand: was für Taktik-, Entwicklungs- und Transferfragen vorliegt, wie frisch es ist und was fehlt.

Schreibt nichts. Zeigt je Quelle das letzte In-Game-Datum und den Abstand zum neuesten Stand im Save, ob der
FMMT-27-Reader (live) erreichbar ist, nicht importierte Rohdateien, ob config/taktik_slots.yaml älter als
taktik.md ist, Teil-Dateien des letzten Such-Snapshots (Zeilen je Teil, Warnung am Exporter-Limit 10.000), offene TODO-Felder in kontext.md, Einträge in log.md ohne Ergebnis und die Saisonbasis der
Per-90-Werte (Snapshots der laufenden Saison und der Vorsaison, Gewicht w; config/saison.yaml).

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
import per90
import spiele  # noqa: E402

IMPORT_EXT = {".csv", ".html", ".htm"}
VERALTET_TAGE = 30  # Quelle liegt so weit hinter dem neuesten Stand -> Hinweis
LIMIT_WARN = 9_999  # FM27-Exporter liefert max. 10.000 Zeilen je Datei (wie import.py)


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
    bekannt = {Path(r[0]).name for r in conn.execute(
        "select source_file from snapshots where save=? union select f.source_file from snapshot_files f "
        "join snapshots s on s.id = f.snapshot_id where s.save=?", (save, save))}  # fmt: skip
    return sorted(p.name for p in raw_dir.iterdir() if p.suffix.lower() in IMPORT_EXT and p.name not in bekannt)


def such_teile(conn, save: str) -> dict | None:
    """Teil-Dateien des letzten Such-Snapshots mit Zeilen je Teil und Limit-Flag (FM27-Exporter max. 10.000).
    Altimporte ohne snapshot_files: eine Datei, Zeilen = Spieler im Snapshot."""
    r = conn.execute(
        "select id, ingame_date, source_file from snapshots where save=? and view_type='suche' "
        "order by ingame_date desc, id desc limit 1", (save,)
    ).fetchone()  # fmt: skip
    if not r:
        return None
    sid, datum, src = r
    teile = [{"datei": f, "zeilen": n} for f, n in conn.execute(
        "select source_file, rows from snapshot_files where snapshot_id=? order by rowid", (sid,))]  # fmt: skip
    alt = not teile or all(t["zeilen"] is None for t in teile)
    if alt:
        n = conn.execute("select count(*) from players where snapshot_id=?", (sid,)).fetchone()[0]
        teile = [{"datei": src, "zeilen": n}]
    for t in teile:
        t["limit"] = (t["zeilen"] or 0) >= LIMIT_WARN
    return {"datum": datum, "snapshot": sid, "teile": teile, "altimport": alt}


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


def saisonbasis(conn, save: str, config_dir=None) -> dict | None:
    """Saisonbasis der Per-90-Werte (per90.load_saison): Saisons, Snapshots je Quelle, Gewicht der Vorsaison."""
    sc = per90.saison_cfg(config_dir)
    snaps = per90.saison_snapshots(conn, save, per90.SAISON_VIEWS, sc["grenze"])
    if not snaps:
        return None
    aktuell = max(snaps)
    vs = per90.vorsaison(aktuell)
    ids_neu, ids_vs = snaps.get(aktuell, {}), snaps.get(vs, {})
    eigene = None
    if "kader" in ids_neu:
        # ohne verliehene eigene Spieler (Club != eigener Verein = häufigster Verein; Leihende nach dem Export)
        sid, datum = ids_neu["kader"]
        mins = sorted(r[0] or 0 for r in conn.execute(
            "SELECT p.minutes FROM players p WHERE p.snapshot_id = ? AND NOT ("
            " p.club IS NOT (SELECT club FROM players WHERE snapshot_id = p.snapshot_id AND club IS NOT NULL"
            "  GROUP BY club ORDER BY COUNT(*) DESC LIMIT 1)"
            " AND EXISTS (SELECT 1 FROM player_info i WHERE i.snapshot_id = p.snapshot_id"
            "  AND i.player_uid = p.player_uid AND i.field = 'ausgeliehen_von')"
            " AND COALESCE(p.loan_end, '9999') >= ?)",
            (sid, datum)))  # fmt: skip
        if mins:
            eigene = {"max": mins[-1], "median": mins[len(mins) // 2]}
    return {**per90.saison_info(aktuell, vs, ids_neu, ids_vs, sc["uebergang"]), "eigene": eigene}


def saison_ausgeben(saison: dict | None) -> None:
    if not saison:
        print("\nSaisonbasis: keine Spieler-Snapshots")
        return
    print(f"\n{per90.saison_text(saison)}")
    e, u = saison.get("eigene"), saison["uebergang"]
    if e:
        w = [max(0.0, 1 - m / u) for m in (e["max"], e["median"])]
        print(f"  Kader {saison['aktuell']}: Min. neu max {e['max']:.0f} (w={w[0]:.2f}), Median {e['median']:.0f} "
              f"(w={w[1]:.2f}); w je Spieler, Mindestminuten gelten auf Vorsaison x w + neu")  # fmt: skip
    if not saison.get("vs"):
        print(f"  keine Snapshots der Vorsaison {saison['vorsaison']}: nur laufende Saison")


def _kurz(s: str, n: int = 70) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def ausgeben(save: str, quellen: list[dict], reader: dict | None, live_geprueft: bool, raw: list[str],
             drift: str | None, todos: list[str], offen: list[dict],
             saison: dict | None = None, teile: dict | None = None) -> None:  # fmt: skip
    neuestes = max((d for q in quellen if (d := _datum(q["letztes"]))), default=None)
    print(f"Datenstand Save '{save}' (neuestes In-Game-Datum in der DB: {neuestes or '-'})\n")
    print(f"{'Quelle':<16}{'Anzahl':>8}{'letztes':>12}{'Tage zurück':>13}{'Zeilen':>9}")
    for q in quellen:
        d = _datum(q["letztes"])
        rueck = (neuestes - d).days if d and neuestes else None
        print(f"{q['quelle']:<16}{q['snapshots']:>8}{q['letztes'] or '-':>12}"
              f"{'' if rueck is None else rueck:>13}{'-' if q['zeilen'] is None else q['zeilen']:>9}")  # fmt: skip
    print("  Zeilen = Spieler im letzten Snapshot; team_matches = Spiele; spieleinsaetze = Spieler mit Spielliste")

    if teile:
        n = len(teile["teile"])
        print(f"\nSuche {teile['datum']} (Snapshot {teile['snapshot']}): {n} Teil-Datei{'en' if n != 1 else ''}"
              + (" (Altimport: Zeilen = Spieler)" if teile["altimport"] else ""))  # fmt: skip
        for t in teile["teile"]:
            flag = "  <- Exporter-Limit erreicht, vermutlich abgeschnitten" if t["limit"] else ""
            print(f"  {t['datei']:<40}{'-' if t['zeilen'] is None else t['zeilen']:>8}{flag}")

    saison_ausgeben(saison)

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
    if teile and (voll := [t["datei"] for t in teile["teile"] if t["limit"]]):
        hinweise.append(
            f"Suche {teile['datum']}: {', '.join(voll)} am Exporter-Limit (10.000) - Liste vermutlich "
            f"abgeschnitten, Export aufteilen ({teile['datum']}_suche_2.csv …) und scripts/import.py"
        )
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
        kontext_todos(sdir / "kontext.md"), log_offen(sdir / "log.md"), saisonbasis(conn, save, a.config_dir),
        such_teile(conn, save),
    )  # fmt: skip


if __name__ == "__main__":
    main()
