"""Live-Import aus dem laufenden FM27 über FMMT-27 (lokaler HTTP-Reader) in db/fm27.sqlite.

Voraussetzung: FM27 läuft, FMMT-27 (github.com/fmoreoo/FMMT-27, GPL-3.0, eigenes Tool) ist
gestartet (`python server.py`, 127.0.0.1:8627). Es wird nur die HTTP-API abgefragt; kein GPL-Code
in diesem Repo, keine Exporte nötig. Snapshot-Typ `live` (Werte exakt aus dem Speicher).

Nicht gespeichert: CA/PA, Persönlichkeit, versteckte Attribute, Positionswerte. Attribute nur für
eigene Spieler (Club ID bzw. Loaned From ID in my_clubs); fremde Spieler haben im Spiel nur
Scouting-Spannen. Mapping + Pflicht-Kalibrierung (Gehalt/Attribut-Skala): config/live_spalten.yaml.

Aufruf:  uv run python scripts/live.py --save werder [--scope competitive|league|all|cups|continental]
Prüfen:  uv run python scripts/live.py --zeige "Name"      (zeigt Rohwerte, schreibt nichts)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fmparse
import namen

_spec = importlib.util.spec_from_file_location(
    "fm_import", Path(__file__).resolve().parent / "import.py"
)
fm_import = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm_import)

DEFAULT_URL = "http://127.0.0.1:8627"
PLACEHOLDER_VALUES = {0, 300_000_000}  # Reader macht daraus None; hier doppelt abgesichert


def api_get(base: str, path: str, timeout: float = 300) -> dict:
    try:
        with urllib.request.urlopen(base.rstrip("/") + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        common.die(
            f"FMMT-27 unter {base} nicht erreichbar ({e}). Läuft FM27 und `python server.py`?"
        )


def own_club_uids(resp: dict) -> set[str]:
    return {str(c["uid"]) for c in resp.get("my_clubs") or [] if c.get("uid") is not None}


def is_own(row: dict, own: set[str]) -> bool:
    return str(row.get("Club ID")) in own or str(row.get("Loaned From ID")) in own


def _num(v) -> float | None:
    return None if v is None or isinstance(v, bool) else float(v)


def convert_row(row: dict, cfg: dict, own: set[str], derived: dict | None = None) -> dict:
    """FMMT-Zeile -> {uid, core, stats, attrs (nur eigene), info}. Rein, ohne DB-Zugriff."""
    mins = _num(row.get("Mins")) or 0.0
    stats: dict[str, float] = {}
    for col, spec in (cfg.get("stats") or {}).items():
        v = _num(row.get(col))
        if v is None:
            continue
        if spec["typ"] == "p90":
            if mins <= 0:
                continue
            v = v * mins / 90
        stats[spec["name"]] = v
    for q in cfg.get("quoten") or []:
        quote, got = _num(row.get(q["quote"])), stats.get(q["zaehler"])
        if quote and got is not None:
            stats[q["name"]] = got / (quote / 100)
    for name, (zaehler, nenner) in (derived or {}).items():  # wie import.py (spalten.yaml)
        if stats.get(nenner):
            stats[name] = stats.get(zaehler, 0.0) / stats[nenner] * 100

    team = row.get("Team") or "unbekannt"
    senior = team in (cfg.get("nur_team") or [team])
    if not senior:
        stats = {}  # Jugend-/Reserve-Stats nicht mit Profis vergleichen (siehe nur_team)

    k = cfg["kern"]
    period = (cfg.get("gehalt") or {}).get("periode")
    wage_raw = _num(row.get(k["wage"]))
    wage = (
        fmparse.to_annual(wage_raw * cfg["gehalt"].get("faktor", 1.0), period)
        if wage_raw is not None and period
        else None
    )
    value = None
    value_raw = row.get(k["value"])
    if value_raw is not None:
        value = fmparse.parse_money(value_raw, ".")
        if value is not None:
            value *= (cfg.get("wert") or {}).get("faktor", 1.0)

    mine = is_own(row, own)
    attrs = None
    names = list((cfg.get("attribute") or {}).values())
    raw_attrs = row.get("Attrs")
    if mine and raw_attrs and len(raw_attrs) == len(names):
        scale = cfg.get("attribut_skala", 5)
        attrs = {n: max(1, round(v / scale)) for n, v in zip(names, raw_attrs)}

    info = {"quelle": "speicher"}
    club_own = str(row.get("Club ID")) in own
    owner_own = str(row.get("Loaned From ID")) in own
    if club_own and (row.get("Loaned From ID") is None or owner_own):
        info["eigen"] = "kader"
    elif club_own:
        info["eigen"] = "leihe_ein"  # bei uns, gehört einem anderen Verein
    elif owner_own:
        info["eigen"] = "leihe_aus"  # gehört uns, spielt anderswo
    info["team"] = team
    # Nur mit dem Fork von FMMT-27 (fm27-assistant-extensions) und nur für eigene Spieler vorhanden.
    if row.get("Squad Role"):
        info["rolle"] = row["Squad Role"]  # wie Export-Spalte "Einsatzzeiten"; bei Leihe ein fehlt sie
    if row.get("Morale") is not None:
        info["moral_wert"] = str(row["Morale"])  # 20-100, Fork-Offset Vertrag+0x5A; Bänder siehe fm27.py im Fork
    if row.get("Loaned From"):
        info["ausgeliehen_von"] = row["Loaned From"]
    return {
        "uid": str(row[k["uid"]]),
        "core": {
            "name": row.get(k["name"]),
            "club": row.get(k["club"]) or None,
            "league": row.get(k["league"]) or None,
            "position": row.get(k["position"]) or None,
            "age": None if row.get(k["age"]) is None else int(row[k["age"]]),
            "minutes": int(mins) if senior and row.get(k["minutes"]) is not None else None,
            "wage": wage,
            "value": value,
            "contract_end": fmparse.parse_date(row.get(k["contract_end"])),
        },
        "stats": stats,
        "attrs": attrs,
        "info": info,
        "own": mine,
    }


def _ingame_date(resp: dict) -> str:
    d = fmparse.parse_date(resp.get("date"))
    if d is None:
        common.die(f"Kein lesbares In-Game-Datum in der Antwort: {resp.get('date')!r}")
    return d


def club_countries(conn, save: str) -> dict[str, str]:
    """Verein -> Land des Vereins aus früheren Exporten (live liefert kein Land)."""
    rows = conn.execute(
        "SELECT p.club, p.club_country FROM players p JOIN snapshots s ON s.id = p.snapshot_id "
        "WHERE s.save = ? AND p.club IS NOT NULL AND p.club_country IS NOT NULL "
        "ORDER BY s.ingame_date, s.id",
        (save,),
    ).fetchall()
    return dict(rows)  # späterer Snapshot überschreibt früheren


def import_live(
    conn, save: str, resp: dict, cfg: dict, warn, derived: dict | None = None, config_dir=None
) -> dict:
    if not (cfg.get("gehalt") or {}).get("periode"):
        common.die(
            "config/live_spalten.yaml: gehalt.periode fehlt. Erst kalibrieren: "
            '`uv run python scripts/live.py --zeige "<Name>"` und gegen die In-Game-Ansicht prüfen.'
        )
    if (cfg["gehalt"]["periode"]) not in ("woche", "monat", "jahr"):
        common.die("gehalt.periode muss woche | monat | jahr sein.")
    date = _ingame_date(resp)
    own = own_club_uids(resp)
    if not own:
        warn(
            "my_clubs leer – keine eigenen Spieler erkannt, es werden keine Attribute gespeichert."
        )
    countries = club_countries(conn, save)
    export, alias = namen.export_namen(conn, save), namen.alias_laden(config_dir)
    n_own = n_attr = 0
    abweichend: list[str] = []
    with conn:
        sid = fm_import._replace_snapshot(conn, save, f"live_{date}", date, "live")
        seen: set[str] = set()
        for row in resp.get("rows") or []:
            c = convert_row(row, cfg, own, derived)
            uid = c["uid"]
            if uid in seen:
                continue
            seen.add(uid)
            p = c["core"]
            anzeige = namen.anzeige_name(uid, p["name"], export, alias)
            if anzeige != p["name"]:
                c["info"]["name_live"] = p["name"]  # Live-Name (Speicher) weicht vom Exportnamen ab
                if c["own"]:
                    abweichend.append(f"{p['name']} -> {anzeige}")
                p["name"] = anzeige
            conn.execute(
                "INSERT OR REPLACE INTO players(snapshot_id, player_uid, name, club, league, "
                "position, age, wage, value, contract_end, minutes, value_min, value_max, "
                "wage_min, wage_max, club_country) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sid, uid, p["name"], p["club"], p["league"], p["position"], p["age"],
                    p["wage"], p["value"], p["contract_end"], p["minutes"],
                    p["value"], p["value"], p["wage"], p["wage"], countries.get(p["club"]),
                ),
            )  # fmt: skip
            for field, val in c["info"].items():
                conn.execute(
                    "INSERT OR REPLACE INTO player_info VALUES(?,?,?,?)", (sid, uid, field, val)
                )
            for name, v in c["stats"].items():
                conn.execute(
                    "INSERT OR REPLACE INTO player_stats VALUES(?,?,?,?)", (sid, uid, name, v)
                )
            if c["attrs"]:
                n_attr += 1
                for attr, v in c["attrs"].items():
                    conn.execute(
                        "INSERT OR REPLACE INTO player_attributes VALUES(?,?,?,?,?,?,?)",
                        (sid, uid, attr, v, 0, v, v),
                    )
            n_own += c["own"]
    n_no_country = sum(
        1 for r in conn.execute("SELECT club_country FROM players WHERE snapshot_id=?", (sid,))
        if r[0] is None
    )  # fmt: skip
    if n_no_country:
        warn(
            f"{n_no_country} Spieler ohne Land des Vereins (kein früherer Export für den Verein) "
            "-> kein Liga-Ranking, Perzentil-Gruppen nur nach Liga-Name."
        )
    if abweichend:
        warn("Live-Namen eigener Spieler durch Exportnamen ersetzt (gleiche uid): " + ", ".join(abweichend))
    return {
        "snapshot": sid,
        "date": date,
        "spieler": len(seen),
        "eigene": n_own,
        "mit_attr": n_attr,
    }


def namen_pruefen(conn, save: str, resp: dict, config_dir=None) -> list[dict]:
    """Eigene Spieler (live), deren Name vom Export abweicht oder die in keinem Export stehen."""
    own = own_club_uids(resp)
    export, alias = namen.export_namen(conn, save), namen.alias_laden(config_dir)
    out = []
    for r in resp.get("rows") or []:
        if not is_own(r, own):
            continue
        uid, live_name = str(r.get("UID")), r.get("Name")
        anzeige, _ = namen.anzeige_quelle(uid, live_name, export, alias)
        if uid not in export:
            out.append({"uid": uid, "live": live_name, "anzeige": anzeige, "befund": "kein Export mit dieser uid"})
        elif namen.name_norm(export[uid]) != namen.name_norm(live_name):
            out.append({"uid": uid, "live": live_name, "anzeige": anzeige, "befund": f"Export: {export[uid]}"})
    return sorted(out, key=lambda z: z["live"] or "")


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--url", default=DEFAULT_URL, help=f"FMMT-27 Server (Default: {DEFAULT_URL})")
    ap.add_argument(
        "--scope",
        default="competitive",
        choices=["competitive", "league", "all", "cups", "continental"],
    )
    ap.add_argument(
        "--nur-mit-minuten",
        action="store_true",
        help="Spieler ohne Einsatzminuten weglassen (Default: alle, mit Profilfeldern)",
    )
    ap.add_argument(
        "--zeige", metavar="NAME", help="Rohzeilen + Umrechnung zeigen, nichts speichern"
    )
    ap.add_argument(
        "--namen",
        action="store_true",
        help="eigene Spieler, deren Live-Name vom Exportnamen abweicht (oder ohne Export), auflisten; nichts speichern",
    )
    a = ap.parse_args(argv)

    cfg = common.load_yaml("live_spalten.yaml", a.config_dir)
    if not cfg:
        common.die("config/live_spalten.yaml fehlt.")
    status = api_get(a.url, "/api/status", timeout=15)
    if not status.get("ok"):
        common.die(f"FMMT-27: {status.get('error', 'kein FM27-Prozess gefunden')}")
    warn = lambda m: print(f"  WARNUNG: {m}", file=sys.stderr)
    if not status.get("build_known"):
        warn(
            f"Spielbuild {status.get('build')} ist dem Reader nicht bekannt – Werte stichprobenartig prüfen."
        )
    print(f"Lese Spieler (scope={a.scope}) … kann ~10 s+ dauern", file=sys.stderr)
    resp = api_get(a.url, f"/api/players?scope={a.scope}" + ("" if a.nur_mit_minuten else "&all=1"))
    if not resp.get("ok"):
        common.die(f"FMMT-27: {resp.get('error', 'Fehler beim Lesen der Spieler')}")
    for w in resp.get("warnings") or []:
        warn(f"Reader: {w}")

    if a.zeige:
        own = own_club_uids(resp)
        needle = a.zeige.casefold()
        hits = [r for r in resp["rows"] if needle in str(r.get("Name", "")).casefold()][:5]
        print(f"Datum {resp.get('date')}, my_clubs={resp.get('my_clubs')}, Treffer: {len(hits)}")
        for r in hits:
            print(
                json.dumps(
                    {k: v for k, v in r.items() if k not in ("Pos Ratings",)}, ensure_ascii=False
                )
            )
            c = convert_row(
                r, cfg, own, common.load_yaml("spalten.yaml", a.config_dir).get("abgeleitet")
            )
            print(
                "  ->",
                json.dumps(
                    {k: c[k] for k in ("core", "stats", "attrs", "own")},
                    ensure_ascii=False,
                    default=str,
                ),
            )
        return

    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    if a.namen:
        for z in namen_pruefen(conn, save, resp, a.config_dir):
            print("  ".join(f"{k}={v}" for k, v in z.items()))
        return
    derived = common.load_yaml("spalten.yaml", a.config_dir).get("abgeleitet") or {}
    res = import_live(conn, save, resp, cfg, warn, derived, a.config_dir)
    print(f"Save={save}  " + "  ".join(f"{k}={v}" for k, v in res.items()))


if __name__ == "__main__":
    main()
