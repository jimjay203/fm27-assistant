"""Prüfbericht zu einem SpielLogger-Mitschnitt (mod/SpielLogger, JSONL).

Beantwortet die Testfragen: Vollständigkeit der Ereignisse, Abdeckung der Positionen, passen die Spieler-IDs zu
den UIDs in der DB, Ballhöhe und rückwirkende Ballposition. Liest nur.

Aufruf: uv run python scripts/spiellog.py [datei.jsonl]   (ohne Datei: neueste im Standardordner)
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import math
import os
import sqlite3
import statistics
from collections import Counter
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DB = WURZEL / "db" / "fm27.sqlite"
FM27 = Path(os.environ.get("FM27_DIR", r"C:\Program Files (x86)\Steam\steamapps\common\Football Manager 27"))
# Teilzeichenketten der Ereignisnamen: grobe Zählung zum Gegenlesen mit dem Spielbericht, keine Spielstatistik
GRUPPEN = ("Goal", "Shot", "Pass", "Cross", "Foul", "Corner", "Tackle", "Header")


def lesen(pfad: Path) -> dict[str, list[dict]]:
    """Zeilen nach Typ gruppiert; eine abgeschnittene letzte Zeile (Absturz) wird gezählt, nicht geworfen."""
    daten: dict[str, list[dict]] = {}
    oeffnen = gzip.open if str(pfad).endswith(".gz") else open
    with oeffnen(pfad, "rt", encoding="utf-8-sig") as f:
        for zeile in f:
            try:
                satz = json.loads(zeile)
                daten.setdefault(satz["t"], []).append(satz)
            except (json.JSONDecodeError, KeyError, TypeError):
                daten.setdefault("defekt", []).append({})
    return daten


def db_namen(db: Path, uids: set[int]) -> dict[int, str]:
    if not uids or not db.exists():
        return {}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        marken = ",".join("?" * len(uids))
        treffer = con.execute(
            f"SELECT player_uid, name FROM players WHERE player_uid IN ({marken})", [str(u) for u in uids]
        )
        return {int(uid): name for uid, name in treffer}
    finally:
        con.close()


def endstand(daten: dict[str, list[dict]]) -> list[dict]:
    """Das Spiel rechnet voraus und ersetzt Einträge (z. B. nach Wechseln): je Listenindex zählt der letzte Stand."""
    je_index = {e.get("i", -n - 1): e for n, e in enumerate(daten.get("ereignis", []))}
    groesse = next((z["ereignisse"] for z in reversed(daten.get("zaehler", [])) if z["ereignisse"] > 0), None)
    if groesse and daten.get("ende"):  # nur bei sauberem Ende ist der letzte Zähler verlässlich
        je_index = {i: e for i, e in je_index.items() if i < groesse}
    return [je_index[i] for i in sorted(je_index)]


def ball_rueck(daten: dict[str, list[dict]]) -> list[dict]:
    """Rückwirkende Ballpositionen: Stichproben (Plugin 0.1) bzw. Ballspur je Zeitscheibe (ab 0.2)."""
    spur = [{"ts": b["von"] + n, "ball": p} for b in daten.get("ball_spur", []) for n, p in enumerate(b["punkte"])]
    return daten.get("ball_rueck", []) + spur


def auswerten(daten: dict[str, list[dict]], db: Path = DB) -> dict:
    ereignisse = endstand(daten)
    frames = daten.get("frame", [])
    aktiv = [f for f in frames if f.get("aktiv") and f.get("ball")]
    zaehler = daten.get("zaehler", [])
    kopf = (daten.get("kopf") or [{}])[0]

    ts_ereignis = sorted(e["ts"] for e in ereignisse)
    luecke = max((b - a for a, b in itertools.pairwise(ts_ereignis)), default=0)

    # Zeitscheiben je Spielsekunde aus den Frames, damit Lücken in Sekunden lesbar sind
    raten = []
    for a, b in itertools.pairwise(frames):
        sekunden = b["zeit"] - a["zeit"]  # Spielsekunden mit Nachkommastellen; min/sek sind zu grob
        if a["periode"] == b["periode"] and 0 < sekunden <= 30 and b["ts"] > a["ts"]:
            raten.append((b["ts"] - a["ts"]) / sekunden)
    rate = statistics.median(raten) if raten else None

    uids = {u for e in ereignisse for u in e.get("spieler", []) if u > 0}
    namen = db_namen(db, uids)
    kader = {s["uid"] for s in daten.get("spieler", []) if s.get("uid", 0) > 0}

    hoehen = [f["ball"][1] for f in aktiv]
    zeiten = sorted(f["zeit"] for f in aktiv if "zeit" in f)
    abstand_s = [b - a for a, b in itertools.pairwise(zeiten)]
    live = {f["ts"]: f["ball"] for f in aktiv}
    rueck = ball_rueck(daten)
    abstaende = [math.dist(r["ball"], live[r["ts"]]) for r in rueck if r["ts"] in live]

    return {
        "kopf": kopf,
        "zeilen": {typ: len(saetze) for typ, saetze in daten.items()},
        "max_stufe": max((z["stufe"] for z in zaehler), default=kopf.get("stufe")),
        "ereignisse": len(ereignisse),
        "ueberholt": len(daten.get("ereignis", [])) - len(ereignisse),
        "ereignisliste_max": max((z["ereignisse"] for z in zaehler), default=None),
        "ereignisarten": Counter(e["name"] for e in ereignisse),
        "gruppen": {g: sum(g.lower() in e["name"].lower() for e in ereignisse) for g in GRUPPEN},
        "ts_bereich": (ts_ereignis[0], ts_ereignis[-1]) if ts_ereignis else None,
        "groesste_luecke_ts": luecke,
        "ts_je_sekunde": rate,
        "groesste_luecke_s": luecke / rate if rate else None,
        "frames": len(frames),
        "frames_aktiv": len(aktiv),
        "messabstand_median_s": statistics.median(abstand_s) if abstand_s else None,
        "luecken_ueber_5s": (sum(a > 5 for a in abstand_s), sum(a for a in abstand_s if a > 5)),
        "minuten_mit_positionen": len({(f["periode"], f["min"]) for f in aktiv}),
        "minuten_gesehen": len({(f["periode"], f["min"]) for f in frames}),
        "uids_ereignisse": len(uids),
        "uids_in_db": len(namen),
        "uids_im_spieltagskader": len(uids & kader),
        "kader": len(kader),
        "beispiele_uid": sorted(namen.items())[:5],
        "ballhoehe": (min(hoehen), max(hoehen)) if hoehen else None,
        "rueck_punkte": len(rueck),
        "rueck_verglichen": len(abstaende),
        "rueck_abstand_median": statistics.median(abstaende) if abstaende else None,
        "fehler": Counter(f"{f.get('wo')}: {f.get('text')}" for f in daten.get("fehler", [])),
        "ende": [e.get("grund") for e in daten.get("ende", [])],
    }


def bericht(e: dict) -> str:
    def zahl(v, stellen=1):
        return "–" if v is None else f"{v:.{stellen}f}"

    z = [
        f"Spiel {e['kopf'].get('spiel_id', '?')} · aufgenommen {e['kopf'].get('zeit', '?')} · Stufe bis {e['max_stufe']}",
        f"Zeilen: {e['zeilen']} · Ende: {', '.join(e['ende']) or 'fehlt (Abbruch?)'}",
        "",
        "1 Ereignisse",
        f"  Endstand {e['ereignisse']} (überholt {e['ueberholt']}) · Liste im Spiel max. {e['ereignisliste_max']} · Arten {len(e['ereignisarten'])}",
        f"  Zeitscheiben {e['ts_bereich']} · größte Lücke {e['groesste_luecke_ts']} (≈ {zahl(e['groesste_luecke_s'])} s)",
        "  Namens-Treffer (nicht = Spielstatistik): " + ", ".join(f"{g} {n}" for g, n in e["gruppen"].items()),
        "  Häufigste: " + ", ".join(f"{name} {n}" for name, n in e["ereignisarten"].most_common(15)),
        "",
        "2 Positionen",
        f"  Frames {e['frames']}, davon mit Positionen {e['frames_aktiv']}",
        f"  Spielminuten mit Positionen {e['minuten_mit_positionen']} von {e['minuten_gesehen']} mitgeschnittenen",
        (f"  Messabstand Median {zahl(e['messabstand_median_s'], 2)} s · Lücken > 5 s: {e['luecken_ueber_5s'][0]}, "
        f"zusammen {zahl(e['luecken_ueber_5s'][1], 0)} s"),
        "",
        "3 Spieler-IDs",
        (f"  in Ereignissen {e['uids_ereignisse']} · in DB {e['uids_in_db']} · im Spieltagskader "
        f"{e['uids_im_spieltagskader']} (Kader {e['kader']})"),
        f"  Beispiele: {e['beispiele_uid']}",
        "",
        "4 Ball",
        f"  Höhe min/max: {e['ballhoehe']}",
        (f"  rückwirkend {e['rueck_punkte']} Punkte, verglichen {e['rueck_verglichen']}, "
        f"Median-Abstand zu live {zahl(e['rueck_abstand_median'], 2)}"),
    ]
    if e["fehler"]:
        z += ["", "Fehler"] + [f"  {n}× {text}" for text, n in e["fehler"].most_common()]
    return "\n".join(z)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("datei", nargs="?", type=Path)
    ap.add_argument("--db", type=Path, default=DB)
    args = ap.parse_args()
    datei = args.datei
    if datei is None:
        dateien = sorted((FM27 / "BepInEx" / "SpielLogger").glob("*.jsonl"))
        if not dateien:
            raise SystemExit("Kein Mitschnitt gefunden – Datei angeben.")
        datei = dateien[-1]
    print(f"Datei: {datei}")
    print(bericht(auswerten(lesen(datei), args.db)))


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    main()
