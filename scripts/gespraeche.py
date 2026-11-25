"""Vorschläge für Spielergespräche: wen loben, wen kritisieren (je Spieler höchstens ein Vorschlag).

Grundlage: erfasste Einsätze (Tabelle spieleinsaetze, scripts/spiele.py bzw. spiel_erfassen.py) für Note im letzten
Teamspiel und Notenschnitt der letzten Einsätze; Moral live (FMMT-Fork, nur mit --live) oder das Feld
"Zufriedenheit" aus dem letzten Kader-Export. Schwellen und Klickpfade: config/gespraeche.yaml.

Erledigte Gespräche stehen in saves/<save>/data/gespraeche.yaml (uid, typ, In-Game-Datum); der Spieler wird danach
für `abklingzeit_tage` nicht mehr vorgeschlagen. Das Gespräch selbst führt Jimmy im Spiel.

Aufruf:  uv run python scripts/gespraeche.py --save werder [--live] [--heute 2027-10-15]
         uv run python scripts/gespraeche.py --save werder --erledigt Kaars lob_leistung --heute 2027-10-15
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import live
import spiele

REIHENFOLGE = ["lob_leistung", "lob_form", "kritik_leistung", "kritik_form"]


def config(config_dir=None) -> dict:
    return common.load_yaml("gespraeche.yaml", config_dir)


# --------------------------------------------------------------------------- Erledigte Gespräche


def _erledigt_datei(save: str) -> Path:
    return common.save_dir(save) / "data" / "gespraeche.yaml"


def erledigt_laden(save: str) -> list[dict]:
    f = _erledigt_datei(save)
    if not f.exists():
        return []
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("gespraeche") or []


def erledigt_speichern(save: str, uid: str, typ: str, datum: str, name: str | None = None,
                       config_dir=None) -> dict:  # fmt: skip
    if typ not in (config(config_dir).get("typen") or {}):
        common.die(f"Unbekannter Gesprächstyp '{typ}'. Möglich: {', '.join(REIHENFOLGE)}")
    try:
        dt.date.fromisoformat(datum)
    except ValueError:
        common.die(f"Datum '{datum}' ist kein ISO-Datum (JJJJ-MM-TT).")
    eintrag = {"datum": datum, "uid": str(uid), "name": name, "typ": typ}
    alle = [*erledigt_laden(save), eintrag]
    f = _erledigt_datei(save)
    f.parent.mkdir(parents=True, exist_ok=True)
    kopf = "# Geführte Spielergespräche (scripts/gespraeche.py, Kaderplaner-Tab Gespräche)\n"
    f.write_text(kopf + yaml.safe_dump({"gespraeche": alle}, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")  # fmt: skip
    return eintrag


# --------------------------------------------------------------------------- Daten


def kader(conn, save: str) -> dict:
    """Letzter Kader-Export: {"datum", "spieler": {uid: name}, "moral": {uid: Zufriedenheit-Text}}."""
    snap = conn.execute(
        "select id, ingame_date from snapshots where save=? and view_type='kader' "
        "order by ingame_date desc, id desc limit 1",
        (save,),
    ).fetchone()
    if not snap:
        return {"datum": None, "spieler": {}, "moral": {}}
    sid, datum = snap
    spieler = {str(u): n for u, n in conn.execute(
        "select player_uid, name from players where snapshot_id=?", (sid,))}  # fmt: skip
    moral = {str(u): t for u, t in conn.execute(
        "select player_uid, text from player_info where snapshot_id=? and field='zufriedenheit'", (sid,))}  # fmt: skip
    return {"datum": datum, "spieler": spieler, "moral": moral}


def namen(conn, save: str, uids) -> dict[str, str]:
    """Neuester bekannter Name je uid (für Spieler, die nicht im letzten Kader-Export stehen)."""
    out = {}
    for u in uids:
        r = conn.execute(
            "select p.name from players p join snapshots s on s.id=p.snapshot_id "
            "where s.save=? and p.player_uid=? and p.name is not null order by s.ingame_date desc limit 1",
            (save, str(u)),
        ).fetchone()
        if r:
            out[str(u)] = r[0]
    return out


def gegner_je_datum(save: str) -> dict[str, str]:
    """Aus den Spielbericht-YAMLs (saves/<save>/data/spiele/*.yaml): {datum: gegner}."""
    out = {}
    for f in sorted((common.save_dir(save) / "data" / "spiele").glob("*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if d.get("datum") and d.get("gegner"):
            out[str(d["datum"])] = str(d["gegner"])
    return out


def moral_live(url: str = live.DEFAULT_URL) -> dict:
    """Moral (20-100) der eigenen Spieler aus dem FMMT-Fork: {"datum", "spieler": {uid: name}, "moral": {uid: int}}."""
    resp = live.api_get(url, "/api/players?scope=competitive&all=1")
    own = live.own_club_uids(resp)
    if not own or not resp.get("rows"):
        common.die(
            "FMMT-27 liefert keine eigenen Spieler (Spielstand in FM27 geladen?). Ohne 'live' gilt der Kader-Export."
        )
    spieler, moral = {}, {}
    for r in resp.get("rows") or []:
        if str(r.get("Club ID")) not in own:
            continue  # nur Spieler, die gerade bei uns sind
        uid = str(r.get("UID") if r.get("UID") is not None else r.get("uid"))
        spieler[uid] = r.get("Name")
        if r.get("Morale") is not None:
            moral[uid] = int(r["Morale"])
    return {"datum": resp.get("date"), "spieler": spieler, "moral": moral}


# --------------------------------------------------------------------------- Regeln


def _moral_niedrig(wert, cfg: dict) -> bool:
    m = cfg.get("moral") or {}
    if wert is None:
        return False
    if isinstance(wert, (int, float)):
        return wert < m.get("live_niedrig_unter", 33)
    return str(wert) in (m.get("niedrig_texte") or [])


def _note(v) -> str:
    return f"{v:.1f}".replace(".", ",")


def vorschlaege(
    einsaetze: pd.DataFrame, spieler: dict[str, str], moral: dict, erledigt: list[dict], cfg: dict,
    heute: dt.date, gegner: dict[str, str] | None = None,
) -> dict:  # fmt: skip
    """Reine Regelauswertung. `einsaetze` wie spiele.einsaetze() (player_uid, datum, eingesetzt, minuten,
    einwechslung, note); `spieler` = aktueller Kader {uid: name}; `moral` = {uid: int|Text}.

    -> {"letztes_spiel": {datum, gegner}, "vorschlaege": [...], "gesperrt": [...], "ohne": int}"""
    gegner = gegner or {}
    ls, fo = cfg.get("letztes_spiel") or {}, cfg.get("form") or {}
    typen = cfg.get("typen") or {}
    sperre = dt.timedelta(days=int(cfg.get("abklingzeit_tage", 14)))

    letzte_gespraeche: dict[str, dict] = {}
    for e in erledigt:
        u = str(e.get("uid"))
        if u not in letzte_gespraeche or str(e["datum"]) > str(letzte_gespraeche[u]["datum"]):
            letzte_gespraeche[u] = e

    g = einsaetze[einsaetze["eingesetzt"] == 1] if not einsaetze.empty else einsaetze
    letztes = max(g["datum"]) if not g.empty else None
    out, gesperrt, ohne = [], [], 0
    for uid, name in spieler.items():
        t = g[g["player_uid"].astype(str) == uid].sort_values("datum") if not g.empty else g
        kandidaten = {}
        if letztes is not None and not t.empty:
            z = t[t["datum"] == letztes]
            if not z.empty and pd.notna(z.iloc[-1]["note"]):
                r = z.iloc[-1]
                n, minuten = float(r["note"]), r["minuten"]
                gg = gegner.get(str(letztes))
                wo = f" vs. {gg}" if gg else ""
                if n >= ls.get("lob_ab", 7.5):
                    kandidaten["lob_leistung"] = f"Note {_note(n)}{wo} ({letztes})"
                elif n <= ls.get("kritik_bis", 6.0):
                    genug = (minuten >= ls.get("kritik_min_minuten", 45)) if pd.notna(minuten) \
                        else not bool(r.get("einwechslung"))  # fmt: skip
                    if genug:
                        kandidaten["kritik_leistung"] = f"Note {_note(n)}{wo} ({letztes})"
            noten = t["note"].dropna().tail(int(fo.get("spiele", 5)))
            if len(noten) >= int(fo.get("min_einsaetze", 3)):
                schnitt = float(noten.mean())
                grund = f"Ø {_note(schnitt)} aus {len(noten)} Einsätzen ({', '.join(_note(x) for x in noten)})"
                if schnitt >= fo.get("lob_ab", 7.2):
                    kandidaten["lob_form"] = grund
                elif schnitt <= fo.get("kritik_bis", 6.4):
                    kandidaten["kritik_form"] = grund
        if not kandidaten:
            ohne += 1
            continue
        typ = next(k for k in REIHENFOLGE if k in kandidaten)
        info = typen.get(typ) or {}
        m = moral.get(uid)
        v = {
            "uid": uid, "name": name, "typ": typ, "art": info.get("art"), "text": info.get("text", typ),
            "pfad": info.get("pfad"), "grund": kandidaten[typ],
            "weitere": [{"typ": k, "text": (typen.get(k) or {}).get("text", k), "grund": kandidaten[k]}
                        for k in REIHENFOLGE if k in kandidaten and k != typ],
            "moral": m, "moral_niedrig": _moral_niedrig(m, cfg), "hinweis": None,
        }  # fmt: skip
        if v["art"] == "kritik" and v["moral_niedrig"]:
            v["hinweis"] = "Moral niedrig: Kritik eher lassen (aus FM24, für FM27 ungeprüft)"
        zuletzt = letzte_gespraeche.get(uid)
        if zuletzt and heute - dt.date.fromisoformat(str(zuletzt["datum"])) < sperre:
            v["gesperrt_bis"] = (dt.date.fromisoformat(str(zuletzt["datum"])) + sperre).isoformat()
            v["zuletzt"] = zuletzt
            gesperrt.append(v)
            continue
        out.append(v)
    out.sort(key=lambda v: (REIHENFOLGE.index(v["typ"]), v["name"] or ""))
    return {
        "letztes_spiel": {"datum": letztes, "gegner": gegner.get(str(letztes)) if letztes else None},
        "vorschlaege": out, "gesperrt": gesperrt, "ohne": ohne,
    }  # fmt: skip


def berechnen(
    conn, save: str, live_url: str | None = None, heute: str | None = None, config_dir=None
) -> dict:
    """Vorschläge für den Save. `live_url`: Kader und Moral live (sonst letzter Kader-Export)."""
    cfg = config(config_dir)
    k = kader(conn, save)
    moral_quelle = {"quelle": "kader", "datum": k["datum"]}
    if live_url:
        lv = moral_live(live_url)
        k = {"datum": lv["datum"], "spieler": lv["spieler"], "moral": lv["moral"]}
        moral_quelle = {"quelle": "live", "datum": lv["datum"]}
    df = spiele.einsaetze(conn, save)
    erledigt = erledigt_laden(save)
    if not heute:
        kandidaten = [k["datum"], *(str(e["datum"]) for e in erledigt)]
        if not df.empty:
            kandidaten.append(max(df["datum"]))
        heute = max((d for d in kandidaten if d), default=dt.date.today().isoformat())
    res = vorschlaege(df, k["spieler"], k["moral"], erledigt, cfg, dt.date.fromisoformat(str(heute)[:10]),
                      gegner_je_datum(save))  # fmt: skip
    res.update(heute=str(heute)[:10], moral_quelle=moral_quelle, einsaetze=spiele.stand(conn, save),
               abklingzeit_tage=cfg.get("abklingzeit_tage", 14))  # fmt: skip
    return res


# --------------------------------------------------------------------------- CLI


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--live", action="store_true", help="Kader und Moral live vom FMMT-27-Reader")
    ap.add_argument("--url", default=live.DEFAULT_URL)
    ap.add_argument(
        "--heute", help="In-Game-Datum JJJJ-MM-TT (Standard: neuestes Datum in den Daten)"
    )
    ap.add_argument(
        "--erledigt", nargs=2, metavar=("NAME", "TYP"), help="Gespräch als geführt eintragen"
    )
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    if a.erledigt:
        name, typ = a.erledigt
        k = kader(conn, save)["spieler"]
        treffer = [(u, n) for u, n in k.items() if n and name.lower() in n.lower()]
        if len(treffer) != 1:
            common.die(
                f"'{name}' passt auf {len(treffer)} Spieler im Kader: {[n for _, n in treffer]}"
            )
        if not a.heute:
            common.die("--heute (In-Game-Datum) angeben.")
        e = erledigt_speichern(save, treffer[0][0], typ, a.heute, treffer[0][1])
        print(f"Eingetragen: {e['name']} {e['typ']} am {e['datum']}")
        return
    res = berechnen(conn, save, a.url if a.live else None, a.heute)
    ls = res["letztes_spiel"]
    mq = res["moral_quelle"]
    print(f"Stand {res['heute']} · letztes erfasstes Spiel {ls['datum']} {ls['gegner'] or ''} · "
          f"Moral: {mq['quelle']} {mq['datum']}")  # fmt: skip
    for titel, liste in (
        ("Vorschläge", res["vorschlaege"]),
        ("Gesperrt (Abklingzeit)", res["gesperrt"]),
    ):
        print(f"\n{titel}: {len(liste)}")
        for v in liste:
            extra = f" · bis {v['gesperrt_bis']}" if v.get("gesperrt_bis") else ""
            hinweis = f" · {v['hinweis']}" if v.get("hinweis") else ""
            print(
                f"  {v['name']:<22} {v['text']:<36} {v['grund']} · Moral {v['moral']}{extra}{hinweis}"
            )
    print(f"\nOhne Anlass: {res['ohne']} Spieler")


if __name__ == "__main__":
    main()
