"""Importiert FM-Exporte (CSV/HTML) aus saves/<save>/data/raw/ in db/fm27.sqlite.

Dateinamen-Konvention:  YYYY-MM-DD_<view_type>[_beschreibung].csv|html
  view_type: kader | suche | scouting | team_stats | spiel
  Beispiel:  2027-01-15_suche_stuermer.csv

Idempotent: erneuter Import derselben Datei ersetzt den Snapshot (keine Duplikate).
Spalten-Mapping: config/spalten.yaml. Unbekannte Spalten werden geloggt und in player_raw gespeichert.
Screenshots (png/jpg): kein OCR -> Claude überführt die Tabelle vorher in CSV.

Aufruf:  uv run python scripts/import.py --save werder
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fmparse

TABLE_EXT = {".csv", ".html", ".htm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".heic", ".webp"}
HOME_AWAY = {
    "h": "H",
    "heim": "H",
    "home": "H",
    "a": "A",
    "auswärts": "A",
    "auswaerts": "A",
    "away": "A",
}


def parse_filename(path: Path) -> tuple[str, str]:
    """-> (ingame_date ISO, view_type). Wirft ValueError bei Verstoß gegen die Konvention."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(.+)$", path.stem)
    if not m:
        raise ValueError(f"{path.name}: erwartet YYYY-MM-DD_<view_type>[_x].csv")
    date, rest = m.groups()
    datetime.strptime(date, "%Y-%m-%d")
    for vt in sorted(common.VIEW_TYPES, key=len, reverse=True):
        if rest == vt or rest.startswith(vt + "_"):
            return date, vt
    raise ValueError(
        f"{path.name}: unbekannter view_type (erlaubt: {', '.join(common.VIEW_TYPES)})"
    )


def read_table(path: Path, sep: str | None = None, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Liest CSV/HTML als Strings. TODO(export): Trennzeichen/Encoding des echten Exports prüfen."""
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(
            path, dtype=str, sep=sep, engine="python", encoding=encoding, keep_default_na=False
        )
    else:
        df = pd.read_html(path, encoding=encoding)[0].astype(str)
    df.columns = [str(c).strip() for c in df.columns]
    return df


class Mapping:
    def __init__(self, cfg: dict):
        self.lookup = {str(k).strip().casefold(): v for k, v in (cfg.get("spalten") or {}).items()}
        self.decimal = (cfg.get("zahlenformat") or {}).get("dezimal", ".")
        self.wage_period = (cfg.get("gehalt") or {}).get("periode")

    def split(self, columns) -> tuple[dict[str, str], list[str]]:
        """-> ({interner Name: Spaltenname}, [unbekannte Spalten])"""
        mapped, unknown = {}, []
        for col in columns:
            internal = self.lookup.get(col.casefold())
            if internal is None:
                unknown.append(col)
            else:
                mapped[internal] = col
        return mapped, unknown


def _text(v) -> str | None:
    t = str(v).strip() if v is not None else ""
    return t or None


def _int(v: float | None) -> int | None:
    return None if v is None else round(v)


def _replace_snapshot(conn, save: str, source_file: str, date: str, view_type: str) -> int:
    old = conn.execute(
        "SELECT id FROM snapshots WHERE save=? AND source_file=?", (save, source_file)
    ).fetchone()
    if old:
        sid = old[0]
        conn.execute(
            "DELETE FROM team_match_stats WHERE match_id IN "
            "(SELECT id FROM team_matches WHERE snapshot_id=?)",
            (sid,),
        )
        conn.execute("DELETE FROM team_matches WHERE snapshot_id=?", (sid,))
        for t in ("players", "player_stats", "player_attributes", "player_raw", "unmapped_columns"):
            conn.execute(f"DELETE FROM {t} WHERE snapshot_id=?", (sid,))
        conn.execute("DELETE FROM snapshots WHERE id=?", (sid,))
    cur = conn.execute(
        "INSERT INTO snapshots(save, ingame_date, source_file, view_type, imported_at) "
        "VALUES(?,?,?,?,?)",
        (save, date, source_file, view_type, datetime.now().isoformat(timespec="seconds")),
    )
    return cur.lastrowid


def import_players(conn, sid: int, df: pd.DataFrame, mp: Mapping, warn) -> dict:
    mapped, unknown = mp.split(df.columns)
    if "name" not in mapped and "uid" not in mapped:
        common.die(
            "spalten.yaml liefert weder 'name' noch 'uid' für diese Datei "
            "(TODO(export): Spalten-Mapping fehlt)."
        )
    if "wage" in mapped and mp.wage_period not in ("woche", "monat", "jahr"):
        common.die(
            "Gehaltsspalte gemappt, aber gehalt.periode in spalten.yaml fehlt "
            "(woche|monat|jahr) – offener Punkt 6."
        )
    dec = mp.decimal
    stat_cols = {
        i: c for i, c in mapped.items() if i not in common.PLAYER_CORE and not i.startswith("attr_")
    }
    attr_cols = {i[5:]: c for i, c in mapped.items() if i.startswith("attr_")}
    n_fallback = n_name_only = n_dup = 0
    seen: set[str] = set()
    for rec in df.to_dict("records"):
        g = {i: rec[c] for i, c in mapped.items() if i in common.PLAYER_CORE}
        bday = fmparse.parse_date(g.get("birthdate"))
        uid = _text(g.get("uid"))
        if uid is None:
            name = _text(g.get("name"))
            if name is None:
                continue
            n_fallback += 1
            if bday is None:
                n_name_only += 1
            uid = f"{name}|{bday}" if bday else name
        if uid in seen:
            n_dup += 1
        seen.add(uid)
        wage = fmparse.to_annual(fmparse.parse_money(g.get("wage"), dec), mp.wage_period or "jahr")
        conn.execute(
            "INSERT OR REPLACE INTO players VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                uid,
                _text(g.get("name")),
                _text(g.get("club")),
                _text(g.get("league")),
                _text(g.get("position")),
                _int(fmparse.parse_number(g.get("age"), dec)),
                wage,
                fmparse.parse_money(g.get("value"), dec),
                fmparse.parse_date(g.get("contract_end")),
                _int(fmparse.parse_number(g.get("minutes"), dec)),
                bday,
                fmparse.parse_number(g.get("team_possession"), dec),
            ),
        )
        for stat, col in stat_cols.items():
            v = fmparse.parse_number(rec[col], dec)
            if v is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO player_stats VALUES(?,?,?,?)", (sid, uid, stat, v)
                )
        for attr, col in attr_cols.items():
            v, masked = fmparse.parse_attribute(rec[col], dec)
            conn.execute(
                "INSERT OR REPLACE INTO player_attributes VALUES(?,?,?,?,?)",
                (sid, uid, attr, v, int(masked)),
            )
        for col in unknown:
            conn.execute(
                "INSERT OR REPLACE INTO player_raw VALUES(?,?,?,?)",
                (sid, uid, col, _text(rec[col])),
            )
    for col in unknown:
        conn.execute("INSERT OR REPLACE INTO unmapped_columns VALUES(?,?)", (sid, col))
    if unknown:
        warn(
            f"{len(unknown)} unbekannte Spalte(n) (in player_raw gespeichert): {', '.join(unknown)}"
        )
    if n_fallback:
        warn(f"{n_fallback} Spieler ohne UID -> Fallback name+geburtsdatum (TODO(export))")
    if n_name_only:
        warn(f"{n_name_only} davon ohne Geburtsdatum -> nur Name als ID (Verwechslungsgefahr)")
    if n_dup:
        warn(f"{n_dup} doppelte Spieler-IDs in der Datei (letzter Eintrag gewinnt)")
    return {"rows": len(seen), "unmapped": len(unknown)}


def import_team(
    conn, sid: int, save: str, file_date: str, df: pd.DataFrame, mp: Mapping, warn
) -> dict:
    mapped, unknown = mp.split(df.columns)
    if "opponent" not in mapped:
        common.die("spalten.yaml liefert kein 'opponent' für diese Teamdatei (TODO(export)).")
    dec = mp.decimal
    nums = [
        c for c in common.TEAM_CORE if c not in ("datum", "opponent", "home_away", "tactic_slot")
    ]
    extra = {i: c for i, c in mapped.items() if i not in common.TEAM_CORE}
    n = 0
    for rec in df.to_dict("records"):
        opp = _text(rec[mapped["opponent"]])
        if opp is None:
            continue
        date = fmparse.parse_date(rec[mapped["datum"]]) if "datum" in mapped else None
        date = date or file_date
        ha = _text(rec[mapped["home_away"]]) if "home_away" in mapped else None
        ha = HOME_AWAY.get(ha.casefold(), ha) if ha else None
        slot = _text(rec[mapped["tactic_slot"]]) if "tactic_slot" in mapped else None
        vals = [fmparse.parse_number(rec[mapped[c]], dec) if c in mapped else None for c in nums]
        conn.execute(
            "DELETE FROM team_match_stats WHERE match_id IN "
            "(SELECT id FROM team_matches WHERE save=? AND ingame_date=? AND opponent=?)",
            (save, date, opp),
        )
        conn.execute(
            "DELETE FROM team_matches WHERE save=? AND ingame_date=? AND opponent=?",
            (save, date, opp),
        )
        cur = conn.execute(
            "INSERT INTO team_matches(snapshot_id, save, ingame_date, opponent, home_away, tactic_slot, "
            + ", ".join(nums)
            + ") VALUES(?,?,?,?,?,?,"
            + ",".join("?" * len(nums))
            + ")",
            (sid, save, date, opp, ha, slot, *vals),
        )
        for stat, col in extra.items():
            v = fmparse.parse_number(rec[col], dec)
            if v is not None:
                conn.execute("INSERT INTO team_match_stats VALUES(?,?,?)", (cur.lastrowid, stat, v))
        n += 1
    for col in unknown:
        conn.execute("INSERT OR REPLACE INTO unmapped_columns VALUES(?,?)", (sid, col))
    if unknown:
        warn(f"{len(unknown)} unbekannte Spalte(n) (nur geloggt): {', '.join(unknown)}")
    return {"rows": n, "unmapped": len(unknown)}


def import_file(
    conn,
    save: str,
    path: Path,
    cfg: dict,
    sep: str | None = None,
    encoding: str = "utf-8-sig",
    warn=None,
) -> dict:
    warn = warn or (lambda m: print(f"  WARNUNG: {m}", file=sys.stderr))
    date, view = parse_filename(path)
    df = read_table(path, sep, encoding)
    mp = Mapping(cfg)
    with conn:
        sid = _replace_snapshot(conn, save, path.name, date, view)
        if view in common.PLAYER_VIEWS:
            res = import_players(conn, sid, df, mp, warn)
        else:
            res = import_team(conn, sid, save, date, df, mp, warn)
    return {"file": path.name, "view": view, "date": date, "snapshot": sid, **res}


def load_leagues(conn, ligen_cfg: dict) -> int:
    rows = list((ligen_cfg.get("ligen") or {}).items())
    with conn:
        conn.executemany("INSERT OR REPLACE INTO leagues VALUES(?,?)", rows)
    return len(rows)


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--file", type=Path, nargs="*", help="Einzelne Dateien statt des ganzen raw-Ordners"
    )
    ap.add_argument("--raw-dir", type=Path, help="Default: saves/<save>/data/raw")
    ap.add_argument("--sep", help="CSV-Trennzeichen (Default: automatisch erkennen)")
    ap.add_argument("--encoding", default="utf-8-sig")
    a = ap.parse_args(argv)

    save = common.resolve_save(a.save)
    cfg = common.load_yaml("spalten.yaml", a.config_dir)
    files = a.file or sorted((a.raw_dir or common.save_dir(save) / "data" / "raw").glob("*"))
    conn = common.connect(a.db)
    n_leagues = load_leagues(conn, common.load_yaml("ligen.yaml", a.config_dir))

    results = []
    for f in files:
        ext = f.suffix.lower()
        if ext in IMAGE_EXT:
            print(
                f"HINWEIS {f.name}: Screenshot – kein OCR im Skript. Claude überführt die Tabelle "
                "zuerst in eine CSV (gleicher Dateiname mit .csv), dann erneut importieren."
            )
        elif ext in TABLE_EXT:
            try:
                print(f"Importiere {f.name} …")
                results.append(import_file(conn, save, f, cfg, a.sep, a.encoding))
            except ValueError as e:
                print(f"  ÜBERSPRUNGEN: {e}", file=sys.stderr)
    if results:
        print(pd.DataFrame(results).to_string(index=False))
    print(
        f"Save={save}  Dateien importiert: {len(results)}  Ligen in config/ligen.yaml: {n_leagues}"
    )


if __name__ == "__main__":
    main()
