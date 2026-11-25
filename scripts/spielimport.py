"""SpielLogger-Mitschnitt übernehmen: Archiv, DB (spiel_logs, spiel_ereignisse, spiel_spieler_kpis) und – wenn
ein F9-Export des Ergebnisbildschirms vorliegt – Spielbericht (YAML + team_matches) wie spiel_erfassen.py.

Zählungen aus Ereignissen sind EIGENE ABLEITUNGEN; die Gegenprobe mit dem Spielbericht wird ausgegeben. Ein
erneuter Import desselben Spiels (Datum + Gegner) ersetzt die alten Zeilen.

Aufruf:  uv run python scripts/spielimport.py [--datei x.jsonl] [--datum 2027-11-07] [--gegner Name]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import namen
import spiel_erfassen
import spielanalyse
import spielbericht
import spieldaten
from spieldaten import Spiel

SCHEMA = """
CREATE TABLE IF NOT EXISTS spiel_logs(  -- importierte SpielLogger-Mitschnitte
  save TEXT NOT NULL, datum TEXT NOT NULL, gegner TEXT NOT NULL, datei TEXT NOT NULL, quelle TEXT NOT NULL,
  gesehen_ts INTEGER NOT NULL, importiert_am TEXT NOT NULL, PRIMARY KEY(save, datum, gegner));
CREATE TABLE IF NOT EXISTS spiel_ereignisse(  -- x/z aus unserer Sicht: wir greifen nach +z an, +x = rechts
  save TEXT NOT NULL, datum TEXT NOT NULL, i INTEGER NOT NULL, ts INTEGER NOT NULL, periode TEXT, sekunde INTEGER,
  name TEXT NOT NULL, kategorie TEXT NOT NULL, uid TEXT, uid2 TEXT, team TEXT, x REAL, y REAL, z REAL,
  entfernung INTEGER, PRIMARY KEY(save, datum, i));
CREATE TABLE IF NOT EXISTS spiel_spieler_kpis(  -- eigene Zählungen aus den Ereignissen
  save TEXT NOT NULL, datum TEXT NOT NULL, player_uid TEXT NOT NULL, kpi TEXT NOT NULL, wert REAL NOT NULL,
  PRIMARY KEY(save, datum, player_uid, kpi));
"""


def slug(datum: str, gegner: str) -> str:
    return f"{datum}_{re.sub(r'[^a-z0-9]+', '-', namen.name_norm(gegner)).strip('-')}"


# ---------------------------------------------------------------------- Zählungen


def schuesse(spiel: Spiel) -> list:
    """Ein Schuss je Schütze und Moment (das Spiel meldet Versuch und Ausgang getrennt)."""
    ergebnis, letzter = [], {}
    for e in spiel.ereignisse:
        if e.kat == "schuss" and e.uids:
            if e.ts - letzter.get(e.uids[0], -100) > 12:
                ergebnis.append(e)
            letzter[e.uids[0]] = e.ts
    return ergebnis


def teamzaehlung(spiel: Spiel) -> dict[str, list[int]]:
    """[Heim, Gast] je Wert, vergleichbar mit dem Spielbericht."""
    z = {k: [0, 0] for k in ("tore", "schuesse", "ecken", "fouls", "gelb")}
    for t in spielanalyse.tore(spiel):
        z["tore"][t.team] += 1
    for e in schuesse(spiel):
        z["schuesse"][spiel.team(e.uids[0])] += 1
    for e in spiel.ereignisse:
        seite = {"Home": 0, "Away": 1}.get(e.seite)
        if e.name == "RestartCorner" and seite is not None:
            z["ecken"][seite] += 1
        # Der Spielbericht zählt als Fouls die zugesprochenen Freistöße (inkl. Abseits) des Gegners
        if e.name in ("RestartFreekick", "RestartIndirectFreekick") and seite is not None:
            z["fouls"][1 - seite] += 1
        if e.name == "YellowCard" and e.uids:
            z["gelb"][spiel.team(e.uids[0])] += 1
    return z


def spieler_kpis(spiel: Spiel) -> Counter:
    k: Counter = Counter()
    ball = [e for e in spiel.ereignisse if e.uids and e.kat not in spielanalyse.STUMM | {"foul", "karte", "tor"}]
    for e, danach in zip(ball, ball[1:] + [None], strict=False):
        uid = e.uids[0]
        if e.kat in ("pass", "flanke"):
            art = "paesse" if e.kat == "pass" else "flanken"
            k[uid, art] += 1
            # angekommen = die nächste Ballaktion gehört demselben Team
            if danach and spiel.team(danach.uids[0]) == spiel.team(uid):
                k[uid, f"{art}_angekommen"] += 1
        elif e.kat in ("abfangen", "zweikampf", "dribbling", "klaerung", "block", "parade"):
            k[uid, e.kat] += 1
    for e in schuesse(spiel):
        k[e.uids[0], "schuesse"] += 1
    for t in spielanalyse.tore(spiel):
        if t.schuetze:
            k[t.schuetze, "tore"] += 1
        if t.vorlage:
            k[t.vorlage, "vorlagen"] += 1
    return k


# ---------------------------------------------------------------------- Zuordnung und Bericht


def bericht_zum_spiel(spiel: Spiel, wir: int, ordner: Path, datum: str | None = None) -> dict | None:
    """Neuester Ergebnisbildschirm, der zum Mitschnitt passt: Datum bzw. Endstand und eigene Aufstellung."""
    if not ordner.exists():
        return None
    eigene = {namen.name_norm(s.name) for s in spiel.spieler.values() if s.team == wir and s.art == "Player"}
    stand = [str(n) for n in teamzaehlung(spiel)["tore"]]
    for b in reversed(spielbericht.alle(ordner)):
        if datum and b["datum"] != datum:
            continue
        aufgestellt = [namen.name_norm(p["spieler"]) for p in b["aufstellung"][wir]]
        if b["werte"].get("tore") == stand and sum(n in eigene for n in aufgestellt) >= 8:
            return b
    return None


def zuordnung(conn, save: str, spiel: Spiel, wir: int, ordner: Path | None = None) -> tuple[str | None, str]:
    """(In-Game-Datum, Gegner) aus früherem Import, Spiel-Setup oder Ergebnisbildschirm."""
    conn.executescript(SCHEMA)
    alt = conn.execute(
        "SELECT datum, gegner FROM spiel_logs WHERE save=? AND quelle=?", (save, spiel.datei.name)
    ).fetchone()
    if alt:
        return alt
    datum = spieldaten.datum_aus_setup(spiel.setup)
    b = bericht_zum_spiel(spiel, wir, ordner or spiel.datei.parent / "bildschirm", datum)
    gegner = (b["gast"] if wir == 0 else b["heim"]) if b else spieldaten.gegner_aus_db(spiel, conn, wir)
    return datum or (b or {}).get("datum"), gegner or "unbekannt"


def bericht_yaml(conn, save: str, spiel: Spiel, wir: int, b: dict, datum: str, gegner: str) -> dict:
    """Ergebnisbildschirm + Mitschnitt -> Dict im Format von spiel_erfassen.py."""
    paar = (lambda v: v) if wir == 0 else (lambda v: v[::-1])
    slot = conn.execute(
        "SELECT tactic_slot FROM team_matches WHERE save=? AND tactic_slot IS NOT NULL ORDER BY ingame_date DESC",
        (save,),
    ).fetchone()
    eigene = {namen.name_norm(s.name): s.uid for s in spiel.spieler.values() if s.team == wir}
    kpis, codes = spieler_kpis(spiel), common.load_yaml("spiel_codes.yaml")
    aufstellung = []
    for p in b["aufstellung"][wir]:
        uid = eigene.get(namen.name_norm(p["spieler"]))
        if uid is None:
            continue
        zeile = {"slot": p["slot"], "spieler": p["spieler"], "uid": uid}
        try:
            spiel_erfassen.rolle_id(p["rolle"] or "", codes)
            zeile["rolle"] = p["rolle"]
        except ValueError:
            pass
        if p["note"]:
            zeile["note"] = float(p["note"].replace(",", "."))
        zeile |= {k: kpis[uid, k] for k in ("tore", "vorlagen") if kpis[uid, k]}
        aufstellung.append(zeile)
    return {
        "datum": dt.date.fromisoformat(datum),
        "gegner": gegner,
        "ort": "H" if wir == 0 else "A",
        "wettbewerb": b["wettbewerb"],
        "taktik_slot": slot[0] if slot else None,
        "werte": {k: paar(v) for k, v in b["werte"].items() if None not in v},
        "aufstellung": aufstellung,
    }


# ---------------------------------------------------------------------- Import


def importieren(conn, save: str, spiel: Spiel, datum: str | None = None, gegner: str | None = None,
                ordner: Path | None = None, archiv: Path | None = None) -> dict:  # fmt: skip
    wir = spieldaten.unser_team(spiel, conn, save)
    d, g = zuordnung(conn, save, spiel, wir, ordner)
    datum, gegner = datum or d, gegner or g
    if not datum:
        raise ValueError("Datum unbekannt: F9 auf dem Ergebnisbildschirm drücken oder --datum angeben.")
    archiv = archiv or common.save_dir(save) / "data" / "raw" / "spiellog"
    archiv.mkdir(parents=True, exist_ok=True)
    ziel = archiv / f"{slug(datum, gegner)}.jsonl.gz"
    if spiel.datei.resolve() != ziel.resolve():
        with open(spiel.datei, "rb") as ein, gzip.open(ziel, "wb") as aus:
            shutil.copyfileobj(ein, aus)
    conn.executescript(SCHEMA)
    with conn:
        for tabelle in ("spiel_logs", "spiel_ereignisse", "spiel_spieler_kpis"):
            conn.execute(f"DELETE FROM {tabelle} WHERE save=? AND datum=?", (save, datum))
        conn.execute(
            "INSERT INTO spiel_logs VALUES(?,?,?,?,?,?,?)",
            (save, datum, gegner, ziel.name, spiel.datei.name, spiel.gesehen,
             dt.datetime.now().isoformat(timespec="seconds")),
        )  # fmt: skip
        for n, e in enumerate(spiel.ereignisse):
            periode, sekunde = spiel.zeit(e.ts)
            p = spiel.ball_bei(e.ts)
            quer, laengs = spiel.lage(wir, e.ts, p) if p else (None, None)
            team = spiel.team_von(e)
            conn.execute(
                "INSERT INTO spiel_ereignisse VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (save, datum, n, e.ts, periode, sekunde, e.name, e.kat,
                 str(e.uids[0]) if e.uids else None, str(e.uids[1]) if len(e.uids) > 1 else None,
                 None if team is None else "wir" if team == wir else "gegner",
                 quer, p[1] if p else None, laengs, e.laenge),
            )  # fmt: skip
        conn.executemany(
            "INSERT INTO spiel_spieler_kpis VALUES(?,?,?,?,?)",
            [(save, datum, str(uid), kpi, v) for (uid, kpi), v in spieler_kpis(spiel).items()],
        )
    b = bericht_zum_spiel(spiel, wir, ordner or spiel.datei.parent / "bildschirm", datum)
    return {"datum": datum, "gegner": gegner, "wir": wir, "archiv": ziel, "bericht": b}


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_common_args(ap)
    ap.add_argument("--datei", type=Path, help="Mitschnitt (Default: neuestes Spiel im Logger-Ordner)")
    ap.add_argument("--datum", help="In-Game-Datum JJJJ-MM-TT, falls nicht erkennbar")
    ap.add_argument("--gegner")
    ap.add_argument("--ohne-bericht", action="store_true", help="Spielbericht nicht erfassen")
    ap.add_argument("--alles", action="store_true")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    spiel = spieldaten.laden(a.datei or spieldaten.neuester(), a.alles, a.config_dir)
    conn = common.connect(a.db)
    try:
        r = importieren(conn, save, spiel, a.datum, a.gegner)
    except ValueError as e:
        common.die(str(e))
        raise SystemExit(1) from e
    wir, b = r["wir"], r["bericht"]
    print(f"{r['datum']} gegen {r['gegner']} ({'H' if wir == 0 else 'A'}) · {len(spiel.ereignisse)} Ereignisse "
          f"bis {spiel.uhr(spiel.gesehen)} · Archiv {r['archiv'].name}")  # fmt: skip
    z = teamzaehlung(spiel)
    print("\n| Wert (Heim : Gast) | aus Ereignissen | Spielbericht |\n|---|---|---|")
    for k, v in z.items():
        soll = b["werte"].get(k) if b else None
        print(f"| {k} | {v[0]} : {v[1]} | {f'{soll[0]} : {soll[1]}' if soll else '–'} |")
    if spiel.unbekannt:
        print("Unbekannte Ereignisse (config/spiel_ereignisse.yaml ergänzen):", dict(spiel.unbekannt))
    if a.ohne_bericht:
        return
    if not b:
        print("Spielbericht fehlt: auf dem Ergebnisbildschirm F9 drücken und erneut importieren.")
        return
    ziel = common.save_dir(save) / "data" / "spiele"
    vorhanden = [f for f in ziel.glob(f"{r['datum']}_*.yaml")]
    if vorhanden:
        print(f"Spielbericht {vorhanden[0].name} existiert schon – nicht überschrieben.")
        return
    d = bericht_yaml(conn, save, spiel, wir, b, r["datum"], r["gegner"])
    datei = ziel / f"{r['datum']}_spiel_{slug(r['datum'], r['gegner']).split('_', 1)[1]}.yaml"
    kopf = f"# Automatisch aus F9-Export {b['datei']} und SpielLogger-Mitschnitt {r['archiv'].name}\n"
    datei.write_text(kopf + yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    e = spiel_erfassen.erfassen(conn, save, datei, config_dir=a.config_dir)
    fehlt = sorted(set(spiel_erfassen.WERTE) - set(d["werte"]))
    print(f"Spielbericht erfasst: {datei.name} · {e['stats']} Teamwerte · {e['einsaetze']} Einsätze"
          f"{' · fehlt: ' + ', '.join(fehlt) if fehlt else ''}")  # fmt: skip


if __name__ == "__main__":
    main()
