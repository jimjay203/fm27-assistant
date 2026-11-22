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
    """spalten.yaml: `"Spalte": name` oder `"Spalte": {name, dezimal?, einheit?, typ?}`.

    dezimal: überschreibt zahlenformat.dezimal für diese Spalte; einheit: Pflicht-Suffix ('km');
    typ: text | date (-> player_info) | einsaetze ('6 (2)' -> Starts/Einwechslungen) |
         zeitraum ('6.7.26 - 30.6.27' -> loan_start/loan_end) |
         dauer ('5 Wochen' -> player_info Text + Stat <name>_tage_n; Monat = 30 Tage, Näherung).
    Text-Werte komplett in Klammern ('( Kerngruppe )') werden entklammert.
    Doppelte Header heißen wie bei pandas: 'Endet', 'Endet.1'.
    """

    def __init__(self, cfg: dict):
        self.specs: dict[str, dict] = {}
        for col, v in (cfg.get("spalten") or {}).items():
            self.specs[str(col).strip().casefold()] = {"name": v} if isinstance(v, str) else dict(v)
        self.decimal = (cfg.get("zahlenformat") or {}).get("dezimal", ".")
        self.wage_period = (cfg.get("gehalt") or {}).get("periode")
        self.derived = cfg.get("abgeleitet") or {}  # name: [zähler, nenner] -> Quote in %
        self.by_internal: dict[str, dict] = {}

    def split(self, columns) -> tuple[dict[str, str], list[str]]:
        """-> ({interner Name: Spaltenname}, [unbekannte Spalten])"""
        mapped, unknown = {}, []
        for col in columns:
            spec = self.specs.get(col.casefold())
            if spec is None:
                unknown.append(col)
            else:
                mapped[spec["name"]] = col
                self.by_internal[spec["name"]] = spec
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
        for t in (
            "players",
            "player_stats",
            "player_attributes",
            "player_info",
            "player_raw",
            "unmapped_columns",
        ):
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
    present = {c.casefold(): c for c in df.columns}
    for key, sp in mp.specs.items():
        # Nur bei Attributen kritisch: eine einzelne Spalte "Freistöße" könnte Stat oder Attribut sein.
        if (
            key.endswith(".1")
            and str(sp["name"]).startswith("attr_")
            and key not in present
            and key[:-2] in present
        ):
            warn(
                f"Spalte '{present[key[:-2]]}' kommt nur einmal vor, spalten.yaml erwartet auch "
                f"'{key}' – Zuordnung prüfen (z. B. Stat oder Attribut?)"
            )
    dec = mp.decimal
    spec = lambda i: mp.by_internal.get(i, {})  # noqa: E731
    kind = {i: spec(i).get("typ") for i in mapped}
    text_cols = {i: c for i, c in mapped.items() if kind[i] in ("text", "date", "dauer")}
    apps_col = next((c for i, c in mapped.items() if kind[i] == "einsaetze"), None)
    period_i, period_col = next(((i, c) for i, c in mapped.items() if kind[i] == "zeitraum"), (None, None))
    stat_cols = {
        i: c
        for i, c in mapped.items()
        if i not in common.PLAYER_CORE
        and not i.startswith("attr_")
        and i not in text_cols
        and kind[i] not in ("einsaetze", "zeitraum")
    }
    attr_cols = {i[5:]: c for i, c in mapped.items() if i.startswith("attr_")}
    n_fallback = n_name_only = n_dup = 0
    seen: set[str] = set()
    bad: dict[str, int] = {}  # Spalte -> Anzahl nicht lesbarer, nicht leerer Zellen
    bad_dates: set[str] = set()

    def num(i: str, v) -> float | None:
        s = spec(i)
        r = fmparse.parse_number(v, s.get("dezimal", dec), s.get("einheit"))
        if r is None and not fmparse.is_null(v):
            bad[mapped[i]] = bad.get(mapped[i], 0) + 1
        return r

    def date(i: str, v) -> str | None:
        r = fmparse.parse_date(v)
        if r is None and not fmparse.is_null(v):
            bad[mapped[i]] = bad.get(mapped[i], 0) + 1
            bad_dates.add(mapped[i])
        return r

    for rec in df.to_dict("records"):
        g = {i: rec[c] for i, c in mapped.items() if i in common.PLAYER_CORE}
        info: dict[str, str] = {}
        bday = date("birthdate", g.get("birthdate")) if "birthdate" in g else None
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
        wage_raw = g.get("wage")
        period = fmparse.money_period(wage_raw)
        if period and mp.wage_period and period != mp.wage_period:
            common.die(
                f"Gehalt '{wage_raw}' ist je {period}, spalten.yaml sagt gehalt.periode="
                f"{mp.wage_period} (Faktor-Fehler vermeiden)."
            )
        wrange = fmparse.parse_money_range(wage_raw, spec("wage").get("dezimal", dec))
        wmin, wmax = (
            tuple(fmparse.to_annual(x, mp.wage_period or "jahr") for x in wrange)
            if wrange
            else (None, None)
        )
        wage = (wmin + wmax) / 2 if wrange else None  # Spanne bei nicht gescouteten Spielern
        if wage is None and not fmparse.is_null(wage_raw):
            bad[mapped["wage"]] = bad.get(mapped["wage"], 0) + 1
        loan_start = loan_end = None
        if period_col and not fmparse.is_null(rec[period_col]):  # "6.7.26 - 30.6.27"
            m = re.fullmatch(r"(.+?)\s+[-–]\s+(.+)", rec[period_col].strip())
            if m:
                loan_start, loan_end = date(period_i, m.group(1)), date(period_i, m.group(2))
            else:
                bad[period_col] = bad.get(period_col, 0) + 1
                bad_dates.add(period_col)
        value_raw = g.get("value")
        vrange = fmparse.parse_money_range(value_raw, spec("value").get("dezimal", dec))
        vmin, vmax = vrange or (None, None)
        if vrange is None and not fmparse.is_null(value_raw):
            info["value"] = _text(value_raw)  # z. B. 'Steht nicht zum Verkauf'
        conn.execute(
            "INSERT OR REPLACE INTO players(snapshot_id, player_uid, name, club, league, position, "
            "age, wage, value, contract_end, minutes, birthdate, team_possession, value_min, "
            "value_max, loan_end, wage_min, wage_max, club_country, loan_start) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sid,
                uid,
                _text(g.get("name")),
                _text(g.get("club")),
                _text(g.get("league")),
                _text(g.get("position")),
                _int(num("age", g.get("age"))) if "age" in g else None,
                wage,
                (vmin + vmax) / 2 if vrange else None,
                date("contract_end", g.get("contract_end")) if "contract_end" in g else None,
                _int(num("minutes", g.get("minutes"))) if "minutes" in g else None,
                bday,
                num("team_possession", g.get("team_possession")) if "team_possession" in g else None,
                vmin,
                vmax,
                (date("loan_end", g.get("loan_end")) if "loan_end" in g else None) or loan_end,
                wmin,
                wmax,
                _text(g.get("club_country")),
                loan_start,
            ),
        )
        for i, col in text_cols.items():
            if kind[i] == "date":
                val = date(i, rec[col])
            else:  # '-', '–', '?' = leer -> kein Eintrag
                val = None if fmparse.is_null(rec[col]) else _text(rec[col])
                if val and (m := re.fullmatch(r"\(\s*(.*?)\s*\)", val)):
                    val = m.group(1) or None  # '( Kerngruppe )' -> 'Kerngruppe'
            if val:
                info[i] = val
        for field, val in info.items():
            conn.execute(
                "INSERT OR REPLACE INTO player_info VALUES(?,?,?,?)", (sid, uid, field, val)
            )
        vals: dict[str, float] = {}
        if apps_col:
            apps = fmparse.parse_apps(rec[apps_col])
            if apps is None and not fmparse.is_null(rec[apps_col]):
                bad[apps_col] = bad.get(apps_col, 0) + 1
            if apps:
                vals["einsaetze_start_n"], vals["einsaetze_ein_n"] = apps
        for i, col in text_cols.items():
            if kind[i] == "dauer" and not fmparse.is_null(rec[col]):
                days = fmparse.parse_duration_days(rec[col])
                if days is None:
                    bad[col] = bad.get(col, 0) + 1
                else:
                    vals[f"{i}_tage_n"] = days
        for stat, col in stat_cols.items():
            v = num(stat, rec[col])
            if v is not None:
                vals[stat] = v
        for name, (zaehler, nenner) in mp.derived.items():
            if vals.get(nenner):
                vals[name] = vals.get(zaehler, 0.0) / vals[nenner] * 100
        for stat, v in vals.items():
            conn.execute("INSERT OR REPLACE INTO player_stats VALUES(?,?,?,?)", (sid, uid, stat, v))
        for attr, col in attr_cols.items():
            v, masked = fmparse.parse_attribute(rec[col], dec)
            lo, hi = fmparse.parse_attribute_range(rec[col], dec) or (None, None)
            conn.execute(
                "INSERT OR REPLACE INTO player_attributes VALUES(?,?,?,?,?,?,?)",
                (sid, uid, attr, v, int(masked), lo, hi),
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
    if bad_dates:
        common.die(
            "Unlesbare Datumswerte in: "
            + ", ".join(sorted(bad_dates))
            + " (falsche Spaltenzuordnung? Doppelte Header = 'Endet', 'Endet.1')."
        )
    if bad:
        warn(
            "Nicht lesbare Werte (-> NULL; Dezimalzeichen/Einheit in spalten.yaml prüfen): "
            + ", ".join(f"{c} ×{n}" for c, n in bad.items())
        )
    return {"rows": len(seen), "unmapped": len(unknown), "unlesbar": sum(bad.values())}


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
            _warn_unranked(conn, sid, warn)
        else:
            res = import_team(conn, sid, save, date, df, mp, warn)
    return {"file": path.name, "view": view, "date": date, "snapshot": sid, **res}


def load_leagues(conn, ligen_cfg: dict) -> tuple[int, int]:
    """-> (Anzahl numerische Stärken `leagues`, Anzahl Ranking-Einträge `league_ranking`)."""
    rows = list((ligen_cfg.get("ligen") or {}).items())
    ranking, seen = [], set()
    for rang, e in enumerate(ligen_cfg.get("ranking") or [], start=1):
        key = (e["liga"], e["land"])
        if key in seen:
            common.die(f"ligen.yaml: '{e['liga']}' ({e['land']}) kommt doppelt vor.")
        seen.add(key)
        ranking.append((e["liga"], e["land"], rang, e.get("ansehen"), e.get("pos")))
    with conn:
        conn.executemany("INSERT OR REPLACE INTO leagues VALUES(?,?)", rows)
        conn.execute("DELETE FROM league_ranking")
        conn.executemany("INSERT INTO league_ranking VALUES(?,?,?,?,?)", ranking)
    return len(rows), len(ranking)


def _warn_unranked(conn, sid: int, warn) -> None:
    """Meldet Liga/Land-Kombinationen des Snapshots, die nicht in league_ranking stehen."""
    if not conn.execute("SELECT 1 FROM league_ranking LIMIT 1").fetchone():
        return
    missing = conn.execute(
        "SELECT DISTINCT p.league, p.club_country FROM players p LEFT JOIN league_ranking lr "
        "ON lr.league = p.league AND lr.country = p.club_country "
        "WHERE p.snapshot_id = ? AND p.league IS NOT NULL AND lr.league IS NULL",
        (sid,),
    ).fetchall()
    if missing:
        warn(
            "Liga ohne Eintrag in config/ligen.yaml (Land fehlt oder abweichend geschrieben?): "
            + ", ".join(f"{lg} ({land or 'Land fehlt'})" for lg, land in missing)
        )


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
    n_strength, n_ranking = load_leagues(conn, common.load_yaml("ligen.yaml", a.config_dir))

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
        f"Save={save}  Dateien importiert: {len(results)}  "
        f"Liga-Ranking: {n_ranking}  Liga-Stärken (--liga-norm): {n_strength}"
    )


if __name__ == "__main__":
    main()
