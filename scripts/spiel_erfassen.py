"""Spiel aus den Werten des FM27-Spielberichts erfassen (Screenshot -> YAML -> DB).

Schreibt je YAML-Datei ein Spiel in team_matches + team_match_stats (gleiche Felder und Stat-Namen wie der Import
der Spiel-Exporte, config/spalten.yaml) und optional die Aufstellung in spieleinsaetze. team.py, stand.py und
spiele.py --zeige werten die Daten ohne Unterschied aus.

Ablage: saves/<save>/data/spiele/YYYY-MM-DD_spiel_<gegner>.yaml (ein Spiel je Datei; Dateiname frei, Datum kommt
aus dem Feld `datum`). Format:

    datum: 2027-08-21
    gegner: RB Leipzig
    ort: A                      # H | A (auch Heim/Auswärts)
    wettbewerb: Bundesliga      # Text; Bundesliga/Liga, DFB-Pokal/Pokal, Europapokal -> Code in spieleinsaetze
    taktik_slot: Standard
    saison: 2027/28             # optional, wird gegen das Datum geprüft (config/saison.yaml)
    werte:                      # [wir, Gegner]; Dezimalkomma als Text erlaubt ("2,29")
      tore: [2, 1]
      ballbesitz: [47, 53]
      schuesse: [11, 11]
      schuesse_aufs_tor: [5, 4]
      xg: [2.29, 1.75]
      ppda: [16.23, 14.64]
      grosschancen: [2, 2]
      ecken: [12, 8]
      prog_paesse: [46, 63]
      passquote: [88, 89]
      flankenquote: [12, 30]
      fouls: [5, 9]
      gelb: [1, 3]
      rot: [0, 1]
      laufleistung: [122, 119]
      notenschnitt: [6.8, 6.7]
    aufstellung:                # optional; Slot wie config/taktik_slots.yaml, Rolle mit Ball als UI-Kürzel
      - {slot: TW, rolle: TW, spieler: Hein, note: 6.9}
      - {slot: RV, rolle: IFV, spieler: Keidel, note: 6.5}
      - {slot: ST, rolle: HRS, spieler: Manneh, note: 7.0, tore: 1}
      - {slot: ST, rolle: HRS, spieler: Itten, einwechslung: true, tore: 1}   # Joker, Note/Minuten unbekannt
    # je Eintrag optional: min, tore, vorlagen, xg, einwechslung, auswechslung, uid (statt Namenssuche)

Regeln:
- Duplikate: ein Spiel gleichen Datums und Gegners wird ersetzt (wie beim Export-Import); ein anderes Spiel am
  selben Datum wird gemeldet. Erneutes Erfassen derselben Datei ersetzt Spiel und Aufstellung.
- Spieler -> player_uid über den neuesten Kader-Export, der den Namen enthält (ganzer Name oder Nachname, ohne
  Akzente); auch abgegebene Spieler aus älteren Exporten. Mehrdeutig/unbekannt -> Abbruch, `uid:` angeben.
- spieleinsaetze: manuelle Zeilen tragen roh = "manuell:<Datei>". Zeilen aus FM27 (spiele.py, roh = Hex) werden
  nicht überschrieben (Live-Daten sind genauer), außer mit --ueberschreiben. Minuten nur, wenn angegeben
  (Spielbericht ohne Wechselzeiten -> NULL, Summen in spiele.je_position zählen sie als 0).
- Ballbesitz: gespeichert wird der eigene Wert (team_matches.possession); Summe != 100 -> Warnung.

Aufruf:  uv run python scripts/spiel_erfassen.py --save werder                 (alle Dateien in data/spiele/)
         uv run python scripts/spiel_erfassen.py --save werder --datei saves/werder/data/spiele/x.yaml
         uv run python scripts/spiel_erfassen.py --save werder --ohne-aufstellung
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fmparse
import namen
import per90

# Schlüssel im YAML -> (Stat für uns, Stat für den Gegner), Namen wie config/spalten.yaml (Teamdatei)
WERTE = {
    "tore": ("goals_for", "goals_against"),
    "ballbesitz": ("possession", None),
    "schuesse": ("shots_for", "shots_against"),
    "schuesse_aufs_tor": ("shots_on_target_for", "shots_on_target_against"),
    "xg": ("xg_for", "xg_against"),
    "ppda": ("ppda_for", "ppda_against"),
    "grosschancen": ("big_chances_for", "big_chances_against"),
    "ecken": ("corners_for", "corners_against"),
    "prog_paesse": ("prog_passes_for", "prog_passes_against"),
    "passquote": ("pass_pct_for", "pass_pct_against"),
    "flankenquote": ("cross_pct_for", "cross_pct_against"),
    "fouls": ("fouls_for", "fouls_against"),
    "gelb": ("yellow_for", "yellow_against"),
    "rot": ("red_for", "red_against"),
    "laufleistung": ("distance_for", "distance_against"),
    "notenschnitt": ("rating_for", "rating_against"),
}

# Slot (config/taktik_slots.yaml) -> Positions-Bits wie in den FM27-Spiellisten (config/spiel_codes.yaml):
# Bit 1 immer gesetzt, 28/29 = linke/rechte Seite einer zentralen Position. Belegt an den erfassten Spiellisten
# 2026/27 (RV 1026, LV 2050, IV r 536875010, IV l 268439554, DM l/r, OM r/z/l, ST).
_B = 1 << 1
SLOT_BITS = {
    "TW": _B | 1 << 8,
    "RV": _B | 1 << 10,
    "IV r": _B | 1 << 12 | 1 << 29,
    "IV l": _B | 1 << 12 | 1 << 28,
    "LV": _B | 1 << 11,
    "DM l": _B | 1 << 15 | 1 << 28,
    "DM r": _B | 1 << 15 | 1 << 29,
    "DM": _B | 1 << 15,
    "OM r": _B | 1 << 19,
    "OM z": _B | 1 << 21,
    "OM l": _B | 1 << 20,
    "ST": _B | 1 << 22,
}
SLOT_ALIAS = {"DM Lynen": "DM l", "DM Svanberg": "DM r"}  # Schlüssel aus taktik_slots.yaml

WETTBEWERB_CODE = {"bundesliga": 16, "liga": 16, "dfb-pokal": 136, "pokal": 136, "europapokal": 131}
ORT = {"h": "H", "heim": "H", "home": "H", "a": "A", "auswärts": "A", "auswaerts": "A", "away": "A"}
MANUELL = "manuell:"


def _zahl(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    return fmparse.parse_number(str(v), ",")


def _datum(v) -> str:
    if isinstance(v, dt.date):
        return v.isoformat()
    d = fmparse.parse_date(str(v))
    if d is None:
        raise ValueError(f"datum unlesbar: {v!r}")
    return d


def lesen(path: Path) -> dict:
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for k in ("datum", "gegner", "werte"):
        if not d.get(k):
            raise ValueError(f"{path.name}: Feld '{k}' fehlt")
    return d


def team_werte(d: dict, warn) -> tuple[dict, dict]:
    """-> (Kernfelder team_matches, Stats team_match_stats)."""
    ort = str(d.get("ort") or "").strip()
    kern = {
        "home_away": ORT.get(ort.casefold(), ort or None),
        "tactic_slot": d.get("taktik_slot"),
        "competition": d.get("wettbewerb"),
    }
    stats = {}
    for key, paar in (d.get("werte") or {}).items():
        if key not in WERTE:
            raise ValueError(f"werte.{key}: unbekannt (erlaubt: {', '.join(WERTE)})")
        if not isinstance(paar, list | tuple) or len(paar) != 2:
            raise ValueError(f"werte.{key}: erwartet [wir, Gegner]")
        wir, geg = (_zahl(x) for x in paar)
        f, g = WERTE[key]
        if key == "ballbesitz" and wir is not None and geg is not None and abs(wir + geg - 100) > 1:
            warn(f"Ballbesitz {wir:g} + {geg:g} != 100")
        for stat, v in ((f, wir), (g, geg)):
            if stat is None:
                continue
            (kern if stat in common.TEAM_CORE else stats)[stat] = v
    return kern, stats


def rolle_id(kuerzel: str, codes: dict) -> int:
    k = namen.name_norm(kuerzel)
    for rid, r in (codes.get("rollen") or {}).items():
        if k in {
            namen.name_norm(r.get("kuerzel")),
            namen.name_norm(r.get("name")),
            namen.name_norm(r.get("enum")),
        }:
            return int(rid)
    raise ValueError(f"Rolle '{kuerzel}' nicht in config/spiel_codes.yaml (kuerzel/name)")


def spieler_uid(conn, save: str, e: dict) -> tuple[str, str]:
    if e.get("uid"):
        return str(e["uid"]), str(e.get("spieler") or e["uid"])
    treffer = namen.uid_fuer_name(conn, save, str(e["spieler"]))
    if not treffer:
        raise ValueError(f"Spieler '{e['spieler']}' in keinem Kader-Export gefunden – uid angeben")
    if len(treffer) > 1:
        raise ValueError(
            f"Spieler '{e['spieler']}' mehrdeutig: {', '.join(f'{n} ({u})' for u, n, _ in treffer)} – uid angeben"
        )
    return treffer[0][0], treffer[0][1]


def aufstellung(conn, save: str, d: dict, codes: dict) -> list[dict]:
    """Aufstellung -> Zeilen für spieleinsaetze (ohne Speichern; Fehler sammeln und gemeinsam melden)."""
    zeilen, fehler = [], []
    wb = WETTBEWERB_CODE.get(str(d.get("wettbewerb") or "").casefold())
    for e in d.get("aufstellung") or []:
        try:
            slot = SLOT_ALIAS.get(e.get("slot"), e.get("slot"))
            bits = e.get("bits") or SLOT_BITS.get(slot)
            if slot and bits is None:
                raise ValueError(f"Slot '{slot}' unbekannt (erlaubt: {', '.join(SLOT_BITS)})")
            uid, name = spieler_uid(conn, save, e)
            zeilen.append({
                "uid": uid, "name": name, "slot": slot, "position_bits": bits,
                "rolle_id": rolle_id(str(e["rolle"]), codes) if e.get("rolle") else None,
                "wettbewerb": wb, "minuten": e.get("min"), "note": _zahl(e.get("note")),
                "tore": e.get("tore", 0), "vorlagen": e.get("vorlagen", 0), "xg": _zahl(e.get("xg")),
                "einwechslung": int(bool(e.get("einwechslung"))), "auswechslung": int(bool(e.get("auswechslung"))),
            })  # fmt: skip
        except (KeyError, ValueError) as ex:
            fehler.append(f"{e}: {ex}")
    if fehler:
        raise ValueError("Aufstellung: " + "; ".join(fehler))
    uids = [z["uid"] for z in zeilen]
    if len(set(uids)) != len(uids):
        raise ValueError("Aufstellung: Spieler doppelt")
    return zeilen


def _snapshot(conn, save: str, quelle: str, datum: str) -> int:
    """Snapshot (view_type spiel) je YAML-Datei; ein früherer Snapshot derselben Datei wird samt Spiel ersetzt."""
    for (sid,) in conn.execute(
        "SELECT id FROM snapshots WHERE save=? AND source_file=?", (save, quelle)
    ).fetchall():
        conn.execute(
            "DELETE FROM team_match_stats WHERE match_id IN (SELECT id FROM team_matches WHERE snapshot_id=?)",
            (sid,),
        )
        conn.execute("DELETE FROM team_matches WHERE snapshot_id=?", (sid,))
        conn.execute("DELETE FROM snapshot_files WHERE snapshot_id=?", (sid,))
        conn.execute("DELETE FROM snapshots WHERE id=?", (sid,))
    sid = conn.execute(
        "INSERT INTO snapshots(save, ingame_date, source_file, view_type, imported_at) VALUES(?,?,?,?,?)",
        (save, datum, quelle, "spiel", dt.datetime.now().isoformat(timespec="seconds")),
    ).lastrowid
    conn.execute("INSERT INTO snapshot_files VALUES(?,?,?)", (sid, quelle, 1))
    return sid


def erfassen(conn, save: str, path: Path, mit_aufstellung=True, ueberschreiben=False, warn=None,
             codes: dict | None = None, config_dir=None) -> dict:  # fmt: skip
    warn = warn or (lambda m: print(f"  WARNUNG: {m}", file=sys.stderr))
    d = lesen(path)
    datum, gegner = _datum(d["datum"]), str(d["gegner"]).strip()
    if d.get("saison"):
        sc = per90.saison_cfg(config_dir)
        soll = per90.saison_von(datum, sc["grenze"])
        if soll != str(d["saison"]):
            raise ValueError(
                f"{path.name}: saison {d['saison']} passt nicht zum Datum {datum} ({soll})"
            )
    kern, stats = team_werte(d, warn)
    codes = codes if codes is not None else common.load_yaml("spiel_codes.yaml", config_dir)
    zeilen = aufstellung(conn, save, d, codes) if mit_aufstellung else []
    andere = conn.execute(
        "SELECT opponent FROM team_matches WHERE save=? AND ingame_date=? AND opponent<>?",
        (save, datum, gegner),
    ).fetchall()
    if andere:
        warn(
            f"am {datum} schon ein Spiel gegen {', '.join(r[0] for r in andere)} erfasst (anderer Gegnername?)"
        )
    quelle = path.name
    gesperrt: list[str] = []
    with conn:
        sid = _snapshot(conn, save, quelle, datum)
        mid = common.write_team_match(conn, sid, save, datum, gegner, kern, stats)
        if mit_aufstellung:
            conn.execute(
                "DELETE FROM spieleinsaetze WHERE save=? AND datum=? AND roh=?",
                (save, datum, MANUELL + quelle),
            )
            jetzt = dt.datetime.now().isoformat(timespec="seconds")
            for z in zeilen:
                alt = conn.execute(
                    "SELECT roh FROM spieleinsaetze WHERE save=? AND player_uid=? AND datum=?",
                    (save, z["uid"], datum),
                ).fetchone()
                if alt and not str(alt[0] or "").startswith(MANUELL) and not ueberschreiben:
                    gesperrt.append(z["name"])
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO spieleinsaetze(save, player_uid, datum, gegner_id, wettbewerb,
                       eingesetzt, position_bits, rolle_id, minuten, einwechslung, auswechslung, note, tore,
                       vorlagen, xg, roh, erfasst_am) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (save, z["uid"], datum, None, z["wettbewerb"], 1, z["position_bits"], z["rolle_id"],
                     z["minuten"], z["einwechslung"], z["auswechslung"], z["note"], z["tore"], z["vorlagen"],
                     z["xg"], MANUELL + quelle, jetzt),
                )  # fmt: skip
    if gesperrt:
        warn(f"Einsätze aus FM27 (spiele.py) behalten, nicht überschrieben: {', '.join(gesperrt)}")
    return {"datei": quelle, "datum": datum, "gegner": gegner, "spiel_id": mid, "stats": len(stats),
            "einsaetze": len(zeilen) - len(gesperrt)}  # fmt: skip


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--datei",
        type=Path,
        nargs="*",
        help="YAML-Dateien (Default: saves/<save>/data/spiele/*.yaml)",
    )
    ap.add_argument(
        "--ohne-aufstellung", action="store_true", help="nur Teamwerte, spieleinsaetze unverändert"
    )
    ap.add_argument("--ueberschreiben", action="store_true",
                    help="auch Einsätze aus FM27 (spiele.py) durch die manuelle Aufstellung ersetzen")  # fmt: skip
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    dateien = a.datei or sorted((common.save_dir(save) / "data" / "spiele").glob("*.yaml"))
    if not dateien:
        common.die(
            f"Keine YAML-Dateien in saves/{save}/data/spiele/ (Format: Kopf von scripts/spiel_erfassen.py)."
        )
    conn = common.connect(a.db)
    fehler = 0
    for f in dateien:
        try:
            r = erfassen(
                conn, save, f, not a.ohne_aufstellung, a.ueberschreiben, config_dir=a.config_dir
            )
            print("  ".join(f"{k}={v}" for k, v in r.items()))
        except ValueError as e:
            fehler += 1
            print(f"ÜBERSPRUNGEN {f.name}: {e}", file=sys.stderr)
    if fehler:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
