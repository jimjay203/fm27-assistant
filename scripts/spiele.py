"""Spiellisten aus FM27 erfassen: letzte 20 Spiele je Spieler mit Position, Rolle, Minuten, Note, Toren, Vorlagen, xG.

Quelle: FMMT-Fork, GET /api/matchlists (reader/matchlists.py dort; liest den Speicher, kein GPL-Code hier). FM27 hält
diese Listen nur für Spieler, die es gerade anzeigt oder vorhält (Spielerbildschirm "Leistung -> Spiele",
offenbar auch Kaderansichten). Wer mehr Spieler erfassen will, blättert im Spiel durch ihre Leistungsbildschirme und
erfasst danach erneut. Bereits Erfasstes bleibt in der DB (Tabelle spieleinsaetze), neue Spiele kommen dazu.

Zuordnung Liste -> Spieler (die Liste enthält keine Spieler-ID): Summe von Minuten, Toren und Vorlagen der Listenspiele
zwischen zwei Kader-Exporten muss genau der Differenz der Saisonwerte des Spielers entsprechen (Schnittmenge über alle
Zeiträume, die die Liste vollständig abdeckt). Bleiben mehrere übrig: Position passt zum Spieler, dann Notenschnitt.
Nicht eindeutig zuordenbare Listen werden gemeldet und nicht gespeichert.

Codes für Position, Rolle, Wettbewerb: config/spiel_codes.yaml.

Aufruf:  uv run python scripts/spiele.py --save werder            (erfassen, Zusammenfassung ausgeben)
         uv run python scripts/spiele.py --save werder --zeige Grüll
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b
import common
import live

# FM-Positionsbezeichnung -> (Positionskürzel wie in benchmark.parse_positions, Seite oder None)
_POS_FM = {"TW": ("GK", None), "V": ("D", None), "FV": ("WB", None), "DM": ("DM", None), "M": ("M", None),
           "OM": ("AM", None), "ST": ("ST", None)}  # fmt: skip


def codes(config_dir=None) -> dict:
    return common.load_yaml("spiel_codes.yaml", config_dir)


def position_bits_liste(bits: int | None, c: dict | None = None) -> list[int]:
    """Positions-Bits ohne Bit 1 und ohne die Seitenbits (28/29, siehe spiel_codes.yaml: ohne_bezeichnung)."""
    ohne = set((c or codes()).get("ohne_bezeichnung") or [1])
    return [i for i in range(32) if bits and bits >> i & 1 and i not in ohne]


def position_label(bits: int | None, c: dict) -> str | None:
    """Bezeichnung wie in der Spalte "Pos." des Spiels, z. B. "V (Z)"; unbekannte Bits als "Position #n"."""
    if not bits:
        return None
    namen = [
        (c.get("positionen") or {}).get(i, {}).get("label") or f"Position #{i}"
        for i in position_bits_liste(bits, c)
    ]
    return " / ".join(namen) or None


def rolle_label(rid: int | None, c: dict, kurz: bool = False) -> str | None:
    """Deutscher Rollenname (bzw. Kürzel) aus spiel_codes.yaml; ohne deutschen Namen der Enum-Name des Spiels."""
    if rid is None:
        return None
    r = (c.get("rollen") or {}).get(int(rid))
    if not r:
        return f"Rolle #{rid}"
    name = r.get("name") or r.get("enum") or f"Rolle #{rid}"
    return (r.get("kuerzel") or name) if kurz else name


def passt_position(label: str | None, positionstext: str | None) -> bool:
    """FM-Positionsbezeichnung (z. B. 'OM (R)') kommt in der Positionsangabe des Spielers vor."""
    if not label or not positionstext or label.startswith("Position #"):
        return False
    kurz, _, rest = label.partition(" ")
    pos = _POS_FM.get(kurz, (kurz, None))[0]
    seite = rest.strip("()").replace("Z", "C") or None
    for p, seiten in b.parse_positions(positionstext):
        if p == pos and (not seite or not seiten or seite in seiten):
            return True
    return False


# --------------------------------------------------------------------------- Abrufen


def abrufen(url: str = live.DEFAULT_URL, schnell: bool = False) -> dict:
    """Spiellisten, die FM27 gerade hält: {"lists", "mode", "seconds"}. Voll: ein Speicherdurchlauf (etwa eine
    Minute); schnell: nur dort, wo zuvor Listen lagen (wenige Sekunden)."""
    res = live.api_get(url, "/api/matchlists" + ("?quick=1" if schnell else ""))
    if not res.get("ok"):
        common.die(f"FMMT-27 /api/matchlists: {res.get('error', 'Fehler')}")
    return res


# --------------------------------------------------------------------------- Zuordnen


def kader_staende(conn, save: str) -> list[tuple[dt.date, dict]]:
    """Je Kader-Export: Datum und {uid: (name, minuten, tore, vorlagen, notenschnitt, position)}."""
    q = """select p.player_uid, p.name, p.minutes, p.position,
              (select value from player_stats s where s.snapshot_id=p.snapshot_id and s.player_uid=p.player_uid and stat='tore'),
              (select value from player_stats s where s.snapshot_id=p.snapshot_id and s.player_uid=p.player_uid and stat='assists'),
              (select value from player_stats s where s.snapshot_id=p.snapshot_id and s.player_uid=p.player_uid and stat='wertung_avg')
           from players p where p.snapshot_id=?"""
    out = []
    for sid, d in conn.execute(
        "select id, ingame_date from snapshots where save=? and view_type='kader' order by ingame_date, id",
        (save,),
    ):
        werte = {
            str(u): (n, m or 0, t or 0, a or 0, w, pos)
            for u, n, m, pos, t, a, w in conn.execute(q, (sid,))
        }  # fmt: skip
        out.append((dt.date.fromisoformat(d), werte))
    return out


def zuordnen(liste: dict, staende: list) -> dict:
    """-> {"uid": str|None, "name", "kandidaten": [namen], "grund": str}."""
    ein = [e for e in liste["entries"] if e.get("played")]
    if not ein:
        return {"uid": None, "kandidaten": [], "grund": "keine Einsätze in der Liste"}
    erstes = dt.date.fromisoformat(liste["entries"][0]["date"])
    leer = (None, 0, 0, 0, None, None)
    kand, fenster = None, 0
    for (d0, w0), (d1, w1) in itertools.pairwise(staende):
        if erstes > d0:
            continue  # Zeitraum nicht vollständig in der Liste
        teil = [e for e in ein if d0 < dt.date.fromisoformat(e["date"]) <= d1]
        soll = (
            sum(e["minutes"] for e in teil),
            sum(e["goals"] for e in teil),
            sum(e["assists"] for e in teil),
        )
        if soll == (0, 0, 0):
            continue  # nichts gespielt: passt auf zu viele
        passt = {
            u for u, v in w1.items()
            if (v[1] - w0.get(u, leer)[1], v[2] - w0.get(u, leer)[2], v[3] - w0.get(u, leer)[3]) == soll
        }  # fmt: skip
        if (
            passt
        ):  # Zeiträume ohne jeden Treffer (z. B. anders gezählte Wettbewerbe) werden übergangen
            fenster += 1
            kand = passt if kand is None else kand & passt
    if not kand:
        return {
            "uid": None,
            "kandidaten": [],
            "grund": "kein Spieler passt zu Minuten/Toren/Vorlagen",
        }
    letzte = staende[-1][1]
    namen = lambda us: sorted(letzte.get(u, ("?",))[0] for u in us)
    if len(kand) > 1:
        # 1) Position der Liste passt zur Positionsangabe des Spielers
        bits = max(
            {e["position_bits"] for e in ein},
            key=lambda x: sum(e["position_bits"] == x for e in ein),
        )
        c = codes()
        lab = position_label(bits, c)
        nach_pos = {u for u in kand if passt_position(lab, letzte.get(u, (None,) * 6)[5])}
        if len(nach_pos) == 1:
            u = next(iter(nach_pos))
            return {
                "uid": u,
                "name": letzte[u][0],
                "kandidaten": namen(kand),
                "grund": f"Position {lab}",
            }
        # 2) Notenschnitt der Liste am nächsten am Saisonschnitt (deutlicher Abstand nötig)
        noten = [e["rating"] for e in ein if e.get("rating")]
        if noten:
            m = sum(noten) / len(noten)
            abst = sorted((abs((letzte[u][4] or 0) - m), u) for u in kand if letzte.get(u, leer)[4])
            if len(abst) >= 2 and abst[1][0] - abst[0][0] >= 0.1:
                u = abst[0][1]
                return {
                    "uid": u,
                    "name": letzte[u][0],
                    "kandidaten": namen(kand),
                    "grund": "Notenschnitt",
                }
        return {"uid": None, "kandidaten": namen(kand), "grund": "mehrdeutig"}
    u = next(iter(kand))
    return {"uid": u, "name": letzte.get(u, ("?",))[0], "kandidaten": namen(kand),
            "grund": f"Minuten/Tore/Vorlagen ({fenster} Zeiträume)"}  # fmt: skip


# --------------------------------------------------------------------------- Speichern und Abfragen


def speichern(conn, save: str, uid: str, liste: dict) -> int:
    jetzt = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for e in liste["entries"]:
        conn.execute(
            """insert or replace into spieleinsaetze(save, player_uid, datum, gegner_id, wettbewerb, eingesetzt,
               position_bits, rolle_id, minuten, einwechslung, auswechslung, note, tore, vorlagen, xg, roh, erfasst_am)
               values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (save, uid, e["date"], e.get("opponent"), e.get("competition"), int(bool(e.get("played"))),
             e.get("position_bits"), e.get("role"), e.get("minutes"), e.get("sub_on"), e.get("sub_off"),
             e.get("rating"), e.get("goals"), e.get("assists"), e.get("xg"), e.get("raw"), jetzt),
        )  # fmt: skip
        n += 1
    conn.commit()
    return n


def erfassen(conn, save: str, listen: list[dict]) -> dict:
    """Listen zuordnen und speichern. Mehrere Listen für denselben Spieler: die mit dem jüngsten Spiel gilt."""
    staende = kader_staende(conn, save)
    if len(staende) < 2:
        common.die(
            "Zur Zuordnung braucht es mindestens zwei Kader-Exporte (Saisonwerte zu zwei Stichtagen)."
        )
    je_spieler, offen = {}, []
    for liste in listen:
        z = zuordnen(liste, staende)
        if z["uid"] is None:
            if z["grund"] != "keine Einsätze in der Liste":
                offen.append({"kandidaten": z["kandidaten"], "grund": z["grund"],
                              "einsaetze": sum(e.get("played", False) for e in liste["entries"])})  # fmt: skip
            continue
        alt = je_spieler.get(z["uid"])
        if not alt or liste["entries"][-1]["date"] > alt[0]["entries"][-1]["date"]:
            je_spieler[z["uid"]] = (liste, z)
    gespeichert = []
    for uid, (liste, z) in je_spieler.items():
        n = speichern(conn, save, uid, liste)
        gespeichert.append({"uid": uid, "name": z["name"], "spiele": n, "grund": z["grund"]})
    return {
        "listen": len(listen),
        "gespeichert": sorted(gespeichert, key=lambda g: g["name"]),
        "offen": offen,
    }


def einsaetze(conn, save: str, uid: str | None = None) -> pd.DataFrame:
    q = "select * from spieleinsaetze where save = ?" + (" and player_uid = ?" if uid else "")
    df = pd.read_sql_query(
        q + " order by player_uid, datum", conn, params=(save, uid) if uid else (save,)
    )
    if df.empty:
        return df
    c = codes()
    df["position"] = df["position_bits"].map(
        lambda v: position_label(int(v), c) if pd.notna(v) else None
    )
    df["rolle"] = df["rolle_id"].map(lambda v: rolle_label(int(v), c) if pd.notna(v) else None)
    df["rolle_kurz"] = df["rolle_id"].map(
        lambda v: rolle_label(int(v), c, kurz=True) if pd.notna(v) else None
    )
    return df


def stand(conn, save: str) -> dict:
    """Wie viel ist erfasst: Spieler, Spiele, letzte Erfassung."""
    n_sp, n_spiele, zuletzt = conn.execute(
        "select count(distinct player_uid), count(*), max(erfasst_am) from spieleinsaetze where save=?",
        (save,),
    ).fetchone()
    return {"spieler": n_sp or 0, "spiele": n_spiele or 0, "zuletzt": zuletzt}


def je_position(df: pd.DataFrame) -> list[dict]:
    """Einsätze je Position und Rolle: Spiele, Minuten, Notenschnitt, Tore, Vorlagen, xG (nur gespielte Spiele)."""
    g = df[df["eingesetzt"] == 1]
    if g.empty:
        return []
    out = []
    for (pos, rolle), t in g.groupby(["position", "rolle"], dropna=False):
        noten = t["note"].dropna()
        out.append({
            "position": pos, "rolle": rolle, "spiele": len(t), "minuten": int(t["minuten"].sum()),
            "note": round(float(noten.mean()), 2) if len(noten) else None, "tore": int(t["tore"].sum()),
            "vorlagen": int(t["vorlagen"].sum()), "xg": round(float(t["xg"].sum()), 2),
        })  # fmt: skip
    return sorted(out, key=lambda r: -r["minuten"])


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--url", default=live.DEFAULT_URL)
    ap.add_argument(
        "--zeige", metavar="NAME", help="erfasste Spiele eines Spielers zeigen (nichts abrufen)"
    )
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    if a.zeige:
        uids = [
            u
            for (u,) in conn.execute(
                "select distinct player_uid from players where name like ?", (f"%{a.zeige}%",)
            )
        ]
        df = einsaetze(conn, save)
        df = df[df["player_uid"].isin(uids)]
        if df.empty:
            common.die(f"Keine erfassten Spiele für '{a.zeige}'.")
        cols = ["datum", "position", "rolle_kurz", "minuten", "einwechslung", "auswechslung", "note", "tore",
                "vorlagen", "xg"]  # fmt: skip
        print(df[cols].to_string(index=False))
        print(pd.DataFrame(je_position(df)).to_string(index=False))
        return
    print("Lese Spiellisten aus FM27 (etwa eine Minute) …")
    res = erfassen(conn, save, abrufen(a.url)["lists"])
    print(f"{res['listen']} Listen gefunden, {len(res['gespeichert'])} Spielern zugeordnet:")
    for g in res["gespeichert"]:
        print(f"  {g['name']}: {g['spiele']} Spiele ({g['grund']})")
    for o in res["offen"]:
        print(
            f"  nicht zugeordnet ({o['grund']}, {o['einsaetze']} Einsätze): {', '.join(o['kandidaten']) or '-'}"
        )


if __name__ == "__main__":
    main()
