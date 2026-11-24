"""Kaderplaner: beste eigene Spieler je Slot einer Formation und Verbesserungen aus der Spielersuche.

Fachlogik ohne Web-Bezug (die Oberfläche ist scripts/webapp.py). Bewertet wird mit dem Rollen-Score aus
scripts/rollen.py (Rollenpaar mit/ohne Ball, Anker = Perzentile 25/55/90 des Vergleichspools, Rollen-Zuordnung
ungeprüft, siehe wissen/rollen-kpis.md). Formationen: config/formationen.yaml.
Key-Attribute je Rollenpaar (scripts/rollen_attr.py, config/rollen_attribute.yaml) werden nur ausgewiesen
(`key` je Zeile): sie ändern weder Score noch Rangfolge. Attribute aus der DB (eigene exakt, fremde als Spanne).

Datenquellen:
- db (Standard): letzter Kader-Snapshot = eigene Spieler, letzter Suche-Snapshot = Kandidaten. Der Vergleichspool
  der Anker ist die Vereinigung beider, also so breit wie die letzte Spielersuche.
- live: FMMT-27-Server (alle Spieler des Saves). `in_suche` markiert Spieler aus dem letzten Suche-Snapshot.
"""

from __future__ import annotations

import math
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b
import common
import ligen
import live
import per90
import rollen
import rollen_attr
import sellkeep
import spiele

SPIELER_FELDER = [
    "uid", "name", "club", "league", "liga_stufe", "position", "age", "minutes", "eigen", "datenbasis",
    "mit", "ohne", "paar", "liga_gewicht", "paar_gew", "vs_top",
    "value", "value_min", "value_max", "wage", "wage_min", "wage_max", "contract_end", "loan_end",
    "minuten_text", "min_neu", "min_vs", "w_vs",  # Saisonbasis (per90.kombinieren)
]  # fmt: skip


# --------------------------------------------------------------------------- Daten


def daten_db(conn, save: str, verein: str | None = None) -> pd.DataFrame:
    """Eigene Spieler (letzter Kader-Snapshot) + Kandidaten (Spielersuche) als ein DataFrame, mit Saisonbasis
    (per90.load_saison): Statistiken aus Vorsaison + laufender Saison, Kernfelder vom neuesten Stand. Spieler nur im
    Kader der Vorsaison (abgegeben) fallen heraus; Spieler nur in der Suche der Vorsaison bleiben Kandidaten."""
    kader = per90.letzter_snapshot(conn, save, "kader")
    suche = per90.letzter_snapshot(conn, save, "suche")
    if not kader:
        common.die(
            f"Kein Kader-Snapshot für Save '{save}'. Kader-Export importieren (scripts/import.py)."
        )
    players, _ = per90.load_saison(conn, save, views=("kader", "suche"))
    saison = players.attrs.get("saison")
    ist_kader = players["snapshot_id"] == kader[0]
    players = players[ist_kader | (players["view_type"] == "suche")].reset_index(drop=True)
    ist_kader = players["snapshot_id"] == kader[0]
    if verein is None:
        verein = sellkeep.verein_aus_kader(players, kader[0])
    datum = max(d for d in (kader[1], suche[1] if suche else None) if d)
    status = sellkeep.squad_status(players, conn, verein, datum)  # Leihende gegen das neueste In-Game-Datum
    # Eigene Spieler nur aus dem Kader-Snapshot; dort stehen auch Verliehene (Status leihe_aus, nicht verfügbar).
    players["eigen"] = status.where(ist_kader)
    players["own"] = players["eigen"].notna()
    # Ein Spieler im Kader und in der Suche: die Kader-Zeile gilt (load_wide behält eine Zeile je uid).
    players["in_suche"] = ~ist_kader
    players["quelle"] = np.where(ist_kader, "kader", "suche")
    players["team"] = (
        "Senior Team"  # Exporte haben kein Team-Feld; Jugend fällt über die Mindestminuten heraus
    )
    players["datenbasis"] = b.datenbasis_spalte(players)
    players["league"] = ligen.mit_land(players)  # "Bundesliga (Österreich)" statt "Bundesliga"
    players = players.rename(columns={"player_uid": "uid"})
    players.attrs["stand"] = {
        "quelle": "db",
        "verein": verein,
        "datum": datum,
        "kader_datum": kader[1],
        "suche_datum": suche[1] if suche else None,
        "saison": saison,
        "saisonbasis": per90.saison_text(saison),
    }
    return players


def daten_live(url: str, conn, save: str, config_dir=None) -> pd.DataFrame:
    """Alle Spieler live vom FMMT-27-Server; `in_suche` = im letzten Suche-Snapshot der DB."""
    df = b.load_live_saison(
        url,
        common.load_yaml("live_spalten.yaml", config_dir),
        common.load_yaml("spalten.yaml", config_dir).get("abgeleitet") or {},
        conn, save, config_dir,
    )  # fmt: skip
    if df.empty:
        common.die("Keine Spielerdaten vom FMMT-27-Server (Save geladen? Reader läuft?).")
    suche = per90.letzter_snapshot(conn, save, "suche")
    uids: set[str] = set()
    if suche:
        uids = {
            str(r[0])
            for r in conn.execute(
                "SELECT player_uid FROM players WHERE snapshot_id = ?", (suche[0],)
            )
        }
    df["in_suche"] = df["uid"].astype(str).isin(uids)
    df["quelle"] = np.where(df["own"], "kader", "live")
    # Live kennt kein Leihende (der Reader liefert nur aktive Leihen): aus dem letzten Kader-Export ergänzen
    kader = per90.letzter_snapshot(conn, save, "kader")
    if kader and "eigen" in df:
        ende = dict(conn.execute(
            "SELECT player_uid, loan_end FROM players WHERE snapshot_id = ? AND loan_end IS NOT NULL", (kader[0],)
        ).fetchall())  # fmt: skip
        leihe = df["eigen"].isin(["leihe_aus", "leihe_ein"])
        alt = df["loan_end"] if "loan_end" in df else pd.Series(None, index=df.index, dtype=object)
        df["loan_end"] = alt.where(alt.notna() | ~leihe, df["uid"].astype(str).map(ende))
    df.attrs["stand"] = {
        "quelle": "live",
        "verein": None,
        "datum": df.attrs.get("date"),
        "suche_datum": suche[1] if suche else None,
        "suche_abgleich": int(df["in_suche"].sum()),
        "saison": df.attrs.get("saison"),
        "saisonbasis": per90.saison_text(df.attrs.get("saison")),
    }
    return df


# --------------------------------------------------------------------------- Kontext


@dataclass
class Kontext:
    df: pd.DataFrame
    rk: dict
    lg: ligen.Ligen
    defaults: dict
    formationen: dict
    slots_taktik: dict
    specs: dict
    anker: dict
    ref: dict
    clubs: list[str]
    stand: dict = field(default_factory=dict)
    luecken: dict = field(default_factory=dict)
    pool_min_stufe: str = "Gut"
    save: str | None = None
    db_path: str | None = None  # None + db=False: kein DB-Zugriff (z. B. Tests)
    db: bool = False
    pools: dict = field(default_factory=dict)  # Vergleichspool je Positionsgruppe (Cache)
    # rollen_positionen.yaml: wählbare Rollen je Position
    positionen: dict = field(default_factory=dict)
    # Key-Attribute (scripts/rollen_attr.py): Quelle, Schwelle des Zielvereins, Attribute je uid (Cache aus der DB;
    # None = keine Attribute in der DB) und In-Game-Datum ihres Snapshots
    ra: dict = field(default_factory=dict)
    attr_stufe: str | None = None
    attr_schwelle: int = 8
    attrs: dict = field(default_factory=dict)
    attr_datum: dict = field(default_factory=dict)


def kontext_bauen(
    df: pd.DataFrame,
    rk: dict,
    lg: ligen.Ligen,
    defaults: dict,
    formationen: dict,
    slots_taktik: dict | None = None,
    pool_min_stufe: str = "Gut",
    anker_min_n: int = 100,
    topclubs: int = 20,
    ra: dict | None = None,
) -> Kontext:
    """Anker und Topclub-Referenz für alle Rollen einmal je Datenladung berechnen.

    `ra` = config/rollen_attribute.yaml (Key-Attribute je Rolle, Liga-Schwellen); None = keine Key-Attribute."""
    specs = rollen.statistik_specs(rk, list(rk["rollen"]))
    anker = rollen.anker_je_gruppe(df, rk, specs, lg, defaults, pool_min_stufe, min_n=anker_min_n)
    clubs = b.topclub_liste(df, topclubs)
    ref = rollen.topclub_referenz_je_gruppe(df, rk, specs, clubs, defaults)
    luecken = {}
    for g, stats in specs.items():
        a = anker[g]
        fehlend = {}
        for st in stats:
            if st in a["stats"]:
                continue
            fehlend[st] = (
                "fehlt in den Daten" if st not in df else a["verworfen"].get(st, "verworfen")
            )
        luecken[g] = {"n_pool": a["n_pool"], "statistiken": fehlend}
    stand = dict(df.attrs.get("stand") or {})
    stand.update(
        n_spieler=len(df),
        n_eigene=int(sellkeep.verfuegbar(df["eigen"]).sum()) if "eigen" in df else 0,  # ohne Verliehene
        n_verliehen=int((df["eigen"] == "leihe_aus").sum()) if "eigen" in df else 0,
        n_suche=int(df["in_suche"].sum()) if "in_suche" in df else 0,
        pool_min_stufe=pool_min_stufe,
        anker_min_n=anker_min_n,
        topclubs=clubs,
    )
    ra = ra or {}
    attr_stufe = rollen_attr.ziel_stufe(df, lg)
    attr_schwelle = rollen_attr.schwelle_fuer_stufe(attr_stufe, ra)
    stand.update(attr_stufe=attr_stufe, attr_schwelle=attr_schwelle)
    return Kontext(
        df=df, rk=rk, lg=lg, defaults=defaults, formationen=formationen,
        slots_taktik=slots_taktik or {}, specs=specs, anker=anker, ref=ref, clubs=clubs,
        stand=stand, luecken=luecken, pool_min_stufe=pool_min_stufe,
        ra=ra, attr_stufe=attr_stufe, attr_schwelle=attr_schwelle,
    )  # fmt: skip


def kontext_laden(
    save: str, quelle: str = "db", verein: str | None = None, url: str = live.DEFAULT_URL,
    db_path=None, config_dir=None, pool_min_stufe: str = "Gut", anker_min_n: int = 100,
) -> Kontext:  # fmt: skip
    if quelle not in ("db", "live"):
        common.die(f"Unbekannte Quelle '{quelle}' (db oder live).")
    conn = common.connect(db_path)
    try:
        df = (
            daten_live(url, conn, save, config_dir)
            if quelle == "live"
            else daten_db(conn, save, verein)
        )
    finally:
        conn.close()
    lg = ligen.Ligen.laden(config_dir)
    if pool_min_stufe not in lg.stufen:
        common.die(f"Unbekannte Liga-Stufe '{pool_min_stufe}'. Möglich: {', '.join(lg.stufen)}")
    ctx = kontext_bauen(
        df,
        common.load_yaml("rollen_kpis.yaml", config_dir),
        lg,
        common.load_yaml("profile.yaml", config_dir).get("defaults", {}),
        common.load_yaml("formationen.yaml", config_dir),
        common.load_yaml("taktik_slots.yaml", config_dir).get("slots") or {},
        pool_min_stufe=pool_min_stufe,
        anker_min_n=anker_min_n,
        ra=rollen_attr.laden(config_dir),
    )
    ctx.stand["save"] = save
    ctx.save, ctx.db_path, ctx.db = save, db_path, True
    ctx.positionen = common.load_yaml("rollen_positionen.yaml", config_dir).get("positionen") or {}
    return ctx


# --------------------------------------------------------------------------- Formationen und Rollen


def rollen_optionen(rk: dict, gruppen: list[str]) -> dict[str, list[str]]:
    """Wählbare Rollen eines Slots: Gruppe passt, Phase mit/std bzw. ohne/std; FM27-Aliasnamen eingeschlossen."""
    out: dict[str, list[str]] = {"mit": [], "ohne": []}
    alias = rk.get("alias_rollen") or {}
    namen = list(rk["rollen"]) + [a for a, z in alias.items() if z in rk["rollen"]]
    for g in gruppen:
        for n in namen:
            r = rk["rollen"][rollen.aufloesen(n, rk)]
            if r["gruppe"] != g:
                continue
            for phase in ("mit", "ohne"):
                if r["phase"] in (phase, "std") and n not in out[phase]:
                    out[phase].append(n)
    return out


def slot_optionen(rk: dict, positionen: dict, slot: dict) -> dict[str, list[str]]:
    """Wählbare Rollen eines Slots: Liste der FM-Position (rollen_positionen.yaml), sonst aus den Gruppen."""
    if "position" not in slot:
        return rollen_optionen(rk, slot["gruppen"])
    pos = positionen.get(slot["position"])
    if not pos:
        common.die(f"Position '{slot['position']}' fehlt in config/rollen_positionen.yaml.")
    for phase in ("mit", "ohne"):
        for n in pos[phase]:
            if rollen.aufloesen(n, rk) not in rk["rollen"]:
                common.die(
                    f"Rolle '{n}' (Position {slot['position']}) fehlt in config/rollen_kpis.yaml "
                    "(auch nicht als alias_rollen)."
                )
    return {"mit": list(pos["mit"]), "ohne": list(pos["ohne"])}


def _standardrolle(rk: dict, optionen: list[str]) -> str | None:
    """Erste Standardrolle (phase std) der Optionen, sonst die erste Option."""
    std = [n for n in optionen if rk["rollen"][rollen.aufloesen(n, rk)]["phase"] == "std"]
    return (std or optionen or [None])[0]


def formationen_meta(ctx: Kontext) -> dict:
    """Formationen mit Slots, Rollenoptionen und Vorbelegung für die Oberfläche."""
    rk, out = ctx.rk, {}
    for name, f in (ctx.formationen.get("formationen") or {}).items():
        vorbel = ctx.slots_taktik if f.get("vorbelegung_aus") else {}
        slots = {}
        for sn, s in f["slots"].items():
            opt = slot_optionen(rk, ctx.positionen, s)
            v = vorbel.get(sn) or s.get("vorbelegung") or {}
            slots[sn] = {
                "position": s.get("position"), "label": s.get("label") or sn,
                "x": s["x"], "y": s["y"], "optionen": opt,
                "mit": v.get("mit") if v.get("mit") in opt["mit"] else _standardrolle(rk, opt["mit"]),
                "ohne": v.get("ohne") if v.get("ohne") in opt["ohne"] else _standardrolle(rk, opt["ohne"]),
            }  # fmt: skip
        out[name] = {"slots": slots}
    return out


# --------------------------------------------------------------------------- Bewertung


@dataclass
class Filter:
    min_minuten: int = 900  # Kandidaten
    min_minuten_eigene: int = 400
    max_alter: int | None = None
    max_wert_mio: float | None = None
    min_stufe: str | None = None  # Kandidaten nur aus Ligen ab dieser Stufe
    gewichtung: str | None = None  # Schema aus ligen.yaml oder 'aus'; None = je Positionsgruppe
    nur_volle_daten: bool = False
    nur_suche: bool = True  # live: nur Spieler aus der letzten Spielersuche
    top_eigene: int = 8
    top_kandidaten: int = 15


def filter_pruefen(ctx: Kontext, f: Filter) -> None:
    if f.min_stufe and f.min_stufe not in ctx.lg.stufen:
        common.die(f"Unbekannte Liga-Stufe '{f.min_stufe}'. Möglich: {', '.join(ctx.lg.stufen)}")
    if f.gewichtung and f.gewichtung != "aus" and f.gewichtung not in ctx.lg.schemata():
        common.die(
            f"Unbekannte Gewichtung '{f.gewichtung}'. Möglich: aus, {', '.join(ctx.lg.schemata())}"
        )


def _rolle(ctx: Kontext, name: str) -> str:
    ziel = rollen.aufloesen(name, ctx.rk)
    if ziel not in ctx.rk["rollen"]:
        common.die(
            f"Rolle '{name}' fehlt in config/rollen_kpis.yaml (auch nicht als alias_rollen)."
        )
    return ziel


def slot_luecken(ctx: Kontext, mit: str, ohne: str) -> list[dict]:
    """Je Rolle die Bausteine, denen Statistiken fehlen (mit Grund); entfallene Bausteine markiert."""
    out = []
    for phase, name in (("mit", mit), ("ohne", ohne)):
        r = ctx.rk["rollen"][name]
        g = r["gruppe"]
        fehlend = ctx.luecken.get(g, {}).get("statistiken", {})
        total = sum(float(w) for w in r["bausteine"].values())
        weg = 0.0
        for bn, w in r["bausteine"].items():
            stats = [s["stat"] for s in ctx.rk["bausteine"][bn]["stats"]]
            miss = {s: fehlend[s] for s in stats if s in fehlend}
            if not miss:
                continue
            entfaellt = len(miss) == len(stats)
            weg += float(w) if entfaellt else 0
            out.append({"phase": phase, "rolle": name, "baustein": bn, "entfaellt": entfaellt,
                        "statistiken": miss})  # fmt: skip
        if out and weg:
            out.append({"phase": phase, "rolle": name, "abdeckung": round(1 - weg / total, 3)})
    return out


def _wert(v):
    if v is None:
        return None
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else round(float(v), 2)
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def _zeilen(ctx: Kontext, sub: pd.DataFrame, mit: str, ohne: str) -> list[dict]:
    if sub.empty:
        return []
    d_m, d_o = rollen.paar_bewerten(sub, mit, ohne, ctx.rk, ctx.anker, ctx.ref, ctx.defaults).attrs[
        "detail"
    ]
    rows = []
    for idx, r in sub.iterrows():
        z = {k: _wert(r.get(k)) for k in SPIELER_FELDER}
        z["uid"] = str(r["uid"])
        z["leihe"] = sellkeep.leihe_text(r.get("eigen"), r.get("loan_end"))  # "verliehen bis ..." / "Leihe bis ..."
        z["bausteine"] = {
            "mit": {k: _wert(v) for k, v in d_m.loc[idx].dropna().items()},
            "ohne": {k: _wert(v) for k, v in d_o.loc[idx].dropna().items()},
        }
        rows.append(z)
    return rows


# --------------------------------------------------------------------------- Key-Attribute (nur ausweisen)


def _key_rolle(ctx: Kontext, name: str, phase: str) -> dict | None:
    d = rollen_attr.rolle_def(name, phase, ctx.ra, ctx.rk)
    return d[1] if d else None


def key_defs(ctx: Kontext, mit_n: str, ohne_n: str) -> dict:
    """Key-Attribute des Rollenpaars (Anzeigenamen wie im Slot) und die Schwelle des Zielvereins."""
    out = {"schwelle": ctx.attr_schwelle, "stufe": ctx.attr_stufe}
    for phase, n in (("mit", mit_n), ("ohne", ohne_n)):
        d = rollen_attr.rolle_def(n, phase, ctx.ra, ctx.rk)
        out[phase] = (
            {"rolle": n, "eintrag": d[0], "key": list(d[1].get("key") or []),
             "preferred": list(d[1].get("preferred") or []), "hinweis": None}
            if d else
            {"rolle": n, "eintrag": None, "key": [], "preferred": [],
             "hinweis": "keine Key-Attribute in der Quelle (config/rollen_attribute.yaml)"}
        )  # fmt: skip
    return out


def attribute_fuer(ctx: Kontext, uids) -> dict[str, dict | None]:
    """Attribute je uid aus der DB (rollen_attr.attribute_laden), gecacht im Kontext; None = keine in der DB.

    Bevorzugt der Snapshot der Spielerzeile (DB-Quelle), sonst der neueste mit Attributen (live: eigene Spieler
    aus dem Live-Snapshot, exakt)."""
    uids = [str(u) for u in uids]
    fehlen = [u for u in dict.fromkeys(uids) if u not in ctx.attrs]
    if fehlen and ctx.db:
        bev = None
        if "snapshot_id" in ctx.df:
            t = ctx.df[ctx.df["uid"].astype(str).isin(set(fehlen))]
            bev = dict(zip(t["uid"].astype(str), t["snapshot_id"], strict=True))
        conn = common.connect(ctx.db_path)
        try:
            attrs, datum = rollen_attr.attribute_laden(conn, ctx.save, fehlen, bev)
        finally:
            conn.close()
        ctx.attrs.update(attrs)
        ctx.attr_datum.update(datum)
    for u in fehlen:
        ctx.attrs.setdefault(u, None)
    return {u: ctx.attrs.get(u) for u in uids}


def key_kennzahlen(ctx: Kontext, mit_n: str, ohne_n: str, uids) -> dict[str, dict]:
    """Je uid: key_mit/key_ohne/pref_mit, key_fehlt x/key_n, key_unsicher, Ausfallliste (rollen_attr.paar).

    exakt = alle bekannten key-Attribute als exakter Wert (eigene Spieler); sonst Spannen (Mitte, "unsicher")."""
    d_m, d_o = _key_rolle(ctx, mit_n, "mit"), _key_rolle(ctx, ohne_n, "ohne")
    keys = list(dict.fromkeys((d_m or {}).get("key", []) + (d_o or {}).get("key", [])))
    out = {}
    for u, a in attribute_fuer(ctx, uids).items():
        p = rollen_attr.paar(a, d_m, d_o, ctx.attr_schwelle)
        z = {k: _wert(p[k]) for k in rollen_attr.SPALTEN if k != "ausfaelle"}
        bekannt = [a[k] for k in keys if a and k in a and rollen_attr._mitte(a[k])[0] is not None]
        z.update(
            attribute=a is not None, text=p["ausfaelle"],
            ausfaelle=rollen_attr.ausfall_liste(a, d_m, d_o, ctx.attr_schwelle) if a else [],
            exakt=bool(bekannt) and all(rollen_attr._ok(v[0]) for v in bekannt),
            datum=ctx.attr_datum.get(u),
        )  # fmt: skip
        out[u] = z
    return out


def key_ergaenzen(ctx: Kontext, zeilen: list[dict], mit_n: str, ohne_n: str) -> None:
    """Ergänzt je Zeile `key` (key_kennzahlen); Rangfolge und Scores bleiben unverändert."""
    kz = key_kennzahlen(ctx, mit_n, ohne_n, [z["uid"] for z in zeilen])
    for z in zeilen:
        z["key"] = kz[z["uid"]]


def slot_bewerten(ctx: Kontext, mit_name: str, ohne_name: str, f: Filter):
    """-> (eigene, kandidaten) als DataFrames, absteigend nach paar_gew."""
    mit, ohne = _rolle(ctx, mit_name), _rolle(ctx, ohne_name)
    a = SimpleNamespace(
        min_minuten=f.min_minuten, nur_volle_daten=f.nur_volle_daten, max_alter=f.max_alter,
        max_wert_mio=f.max_wert_mio, gewichtung=f.gewichtung, min_stufe=f.min_stufe,
    )  # fmt: skip
    own, cand = rollen.kandidaten_slot(
        ctx.df, mit, ohne, ctx.rk, ctx.anker, ctx.ref, ctx.defaults, ctx.lg, a, f.min_minuten_eigene
    )
    if f.nur_suche and "in_suche" in cand:
        cand = cand[cand["in_suche"]]
    key = ["paar_gew", "paar"]
    own = own.sort_values(key, ascending=False, na_position="last")
    cand = cand.sort_values(key, ascending=False, na_position="last")
    return mit, ohne, own, cand


def ohne_wertung(ctx: Kontext, mit: str, bewertet: pd.DataFrame, f: Filter) -> list[dict]:
    """Verfügbare eigene Spieler der Positionsgruppe, die keinen Score haben, mit Grund (Verliehene: verliehen())."""
    rules = ctx.rk["positionsgruppen"][ctx.rk["rollen"][mit]["gruppe"]]
    df = ctx.df
    da = df["eigen"] != "leihe_aus" if "eigen" in df else True
    sub = df[df["own"] & da & df["position"].map(lambda p: b.position_ok(p, rules))]
    sub = sub[~sub["uid"].astype(str).isin(set(bewertet["uid"].astype(str)))]
    out = []
    for _, r in sub.sort_values("minutes", ascending=False).iterrows():
        mins = r.get("minutes")
        grund = (
            f"{0 if pd.isna(mins) else int(mins)} Min. (< {f.min_minuten_eigene})"
            if pd.isna(mins) or mins < f.min_minuten_eigene
            else "zu wenige Statistiken (Abdeckung < 60 %)"
        )
        out.append({"uid": str(r["uid"]), "name": r["name"], "position": r["position"],
                    "minutes": _wert(mins), "eigen": _wert(r.get("eigen")), "grund": grund,
                    "leihe": sellkeep.leihe_text(r.get("eigen"), r.get("loan_end"))})  # fmt: skip
    return out


def verliehen(ctx: Kontext, mit: str) -> list[dict]:
    """Verliehene eigene Spieler der Positionsgruppe: nicht verfügbar, nur zum Im-Blick-Behalten (Leihrückkehrer)."""
    if "eigen" not in ctx.df:
        return []
    rules = ctx.rk["positionsgruppen"][ctx.rk["rollen"][mit]["gruppe"]]
    df = ctx.df
    sub = df[(df["eigen"] == "leihe_aus") & df["position"].map(lambda p: b.position_ok(p, rules))]
    return [
        {"uid": str(r["uid"]), "name": r["name"], "position": _wert(r.get("position")), "club": _wert(r.get("club")),
         "minutes": _wert(r.get("minutes")), "loan_end": _wert(r.get("loan_end")),
         "leihe": sellkeep.leihe_text("leihe_aus", r.get("loan_end"))}
        for _, r in sub.sort_values("name").iterrows()
    ]  # fmt: skip


# --------------------------------------------------------------------------- Spielersuche


@dataclass
class Suche:
    text: str = ""  # Teil von Name oder Verein (ohne Groß-/Kleinschreibung und Akzente)
    min_alter: int | None = None
    max_alter: int | None = None
    max_wert_mio: float | None = None
    min_stufe: str | None = None  # nur Ligen ab dieser Stufe (eigene Spieler immer)
    gewichtung: str | None = None
    min_minuten: int = 900
    nur_volle_daten: bool = False
    nur_suche: bool = False  # nur Spieler aus der letzten Spielersuche (eigene immer)
    eigene: bool = True  # eigene Spieler mit anzeigen
    # mehr fehlende Key-Attribute ausblenden (Spieler ohne Attribute bleiben drin)
    key_max_fehlt: int | None = None
    limit: int = 150


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s) if isinstance(s, str) else "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def suche(ctx: Kontext, mit_name: str, ohne_name: str, s: Suche) -> dict:
    """Alle Spieler der geladenen Daten für ein Rollenpaar, nach Score; mit Text: dazu Treffer ohne Score + Grund."""
    filter_pruefen(ctx, Filter(min_stufe=s.min_stufe, gewichtung=s.gewichtung))
    mit, ohne = _rolle(ctx, mit_name), _rolle(ctx, ohne_name)
    df = ctx.df
    text = _norm(s.text.strip())
    if text:
        treffer = df["name"].map(_norm).str.contains(text, regex=False)
        if "club" in df:
            treffer |= df["club"].map(_norm).str.contains(text, regex=False)
        df = df[treffer]
    a = SimpleNamespace(
        min_minuten=s.min_minuten, nur_volle_daten=s.nur_volle_daten, max_alter=s.max_alter,
        max_wert_mio=s.max_wert_mio, gewichtung=s.gewichtung, min_stufe=s.min_stufe,
    )  # fmt: skip
    own, cand = rollen.kandidaten_slot(  # Suche: verliehene eigene Spieler mit Hinweis "verliehen bis ..."
        df, mit, ohne, ctx.rk, ctx.anker, ctx.ref, ctx.defaults, ctx.lg, a, s.min_minuten, verliehene=True
    )
    if s.nur_suche and "in_suche" in cand:
        cand = cand[cand["in_suche"]]
    if s.min_alter is not None:
        cand = cand[cand["age"] >= s.min_alter]
    teile = [cand]
    if s.eigene:
        if s.min_alter is not None:
            own = own[own["age"] >= s.min_alter]
        if s.max_alter is not None:
            own = own[own["age"] <= s.max_alter]
        teile.insert(0, own)
    alle = pd.concat(teile).sort_values(["paar_gew", "paar"], ascending=False, na_position="last")
    key_info = {"max_fehlt": s.key_max_fehlt, "ausgeblendet": 0, "ohne_attribute": None}
    if s.key_max_fehlt is not None:
        kz = key_kennzahlen(ctx, mit_name, ohne_name, alle["uid"])
        fehlt = [kz[str(u)]["key_fehlt"] for u in alle["uid"]]
        ok = np.array([f is None or f <= s.key_max_fehlt for f in fehlt], dtype=bool)
        key_info.update(ausgeblendet=int((~ok).sum()), ohne_attribute=sum(f is None for f in fehlt))
        key_weg = set(alle.loc[~ok, "uid"].astype(str))
        alle = alle[ok]
    else:
        key_weg = set()
    ohne_score = []
    if text:
        rules = ctx.rk["positionsgruppen"][ctx.rk["rollen"][mit]["gruppe"]]
        rest = df[~df["uid"].astype(str).isin(set(alle["uid"].astype(str)))]
        for _, r in rest.sort_values("minutes", ascending=False).head(30).iterrows():
            mins = r.get("minutes")
            if str(r["uid"]) in key_weg:
                grund = (
                    f"mehr als {s.key_max_fehlt} Key-Attribute unter Schwelle {ctx.attr_schwelle}"
                )
            elif r.get("team") != "Senior Team":
                grund = "nicht im Profikader"
            elif not b.position_ok(r.get("position"), rules):
                grund = "Position passt nicht zur Rolle"
            elif pd.isna(mins) or mins < s.min_minuten:
                grund = f"{0 if pd.isna(mins) else int(mins)} Min. (< {s.min_minuten})"
            else:
                grund = "Filter oder zu wenige Statistiken"
            ohne_score.append({
                "uid": str(r["uid"]), "name": r.get("name"), "club": _wert(r.get("club")),
                "position": _wert(r.get("position")), "age": _wert(r.get("age")), "minutes": _wert(mins),
                "eigen": _wert(r.get("eigen")), "grund": grund,
                "leihe": sellkeep.leihe_text(r.get("eigen"), r.get("loan_end")),
            })  # fmt: skip
    treffer = _zeilen(ctx, alle.head(s.limit), mit, ohne)
    key_ergaenzen(ctx, treffer, mit_name, ohne_name)
    return {
        "mit": mit_name, "ohne": ohne_name, "gewertet_als": {"mit": mit, "ohne": ohne},
        "treffer": treffer, "n_treffer": len(alle), "ohne_score": ohne_score, "limit": s.limit,
        "key": {**key_defs(ctx, mit_name, ohne_name), "filter": key_info},
    }  # fmt: skip


def aufstellung(eigene: dict[str, pd.DataFrame]) -> dict[str, str | None]:
    """Beste eigene Elf ohne Doppelbesetzung: greedy über (Slot, Spieler) absteigend nach paar_gew.

    Verliehene Spieler (eigen = leihe_aus) werden nicht gesetzt (slot_bewerten lässt sie schon weg)."""
    paare = []
    for slot, df in eigene.items():
        for _, r in df.iterrows():
            if r.get("eigen") == "leihe_aus" or pd.isna(r.get("paar_gew")):
                continue
            paare.append((float(r["paar_gew"]), slot, str(r["uid"])))
    paare.sort(key=lambda t: -t[0])
    out: dict[str, str | None] = {s: None for s in eigene}
    vergeben: set[str] = set()
    for _, slot, uid in paare:
        if out[slot] is None and uid not in vergeben:
            out[slot] = uid
            vergeben.add(uid)
    return out


SEITEN_BIT = {"L": 28, "R": 29}  # Seite innerhalb einer zentralen Position (config/spiel_codes.yaml)
MIN_MINUTEN_POSITION = 270  # darunter zählt ein Spieler auf der Position nicht als "dort gespielt" (3 volle Spiele)


def slot_seite(slot: dict) -> str | None:
    """Seite eines Slots auf dem Feld: L/R nach x (50 = Mitte, keine Seite)."""
    return "L" if slot["x"] < 50 else "R" if slot["x"] > 50 else None


def aufstellung_einsaetze(
    eigene: dict[str, pd.DataFrame], meta: dict[str, dict], info: dict[str, pd.DataFrame]
) -> tuple[dict[str, str | None], dict[str, dict]]:
    """Elf wie bisher gespielt: je Slot der Spieler mit den meisten erfassten Minuten auf der FM-Position des Slots.

    Gewicht = Minuten auf der Position + halbe Minuten auf derselben Seite (trennt z. B. linken und rechten IV).
    Zählt erst ab MIN_MINUTEN_POSITION, damit Kurzeinsätze nicht einen nicht erfassten Stammspieler verdrängen.
    Greedy ohne Doppelbesetzung; nur Spieler, die für den Slot bewertet sind. Slots ohne passende Einsätze
    werden mit den übrigen Spielern nach Score besetzt. Rückgabe: Elf und je Slot der Grund."""
    paare = []
    for slot, df in eigene.items():
        label, seite = fm_position(meta[slot]), slot_seite(meta[slot])
        for _, r in df.iterrows():
            uid = str(r["uid"])
            t = info.get(uid)
            if t is None or r.get("eigen") == "leihe_aus" or pd.isna(r.get("paar_gew")):
                continue
            m = t[t["position"] == label]
            minuten = float(m["minuten"].sum())
            if minuten < MIN_MINUTEN_POSITION:
                continue
            gleiche_seite = 0.0
            if seite:
                bits = m["position_bits"].fillna(0).to_numpy(dtype="int64")
                gleiche_seite = float(m["minuten"].to_numpy()[((bits >> SEITEN_BIT[seite]) & 1) == 1].sum())
            paare.append((minuten + 0.5 * gleiche_seite, slot, uid, minuten, len(m)))
    paare.sort(key=lambda t: -t[0])
    elf: dict[str, str | None] = {s: None for s in eigene}
    grund: dict[str, dict] = {}
    vergeben: set[str] = set()
    for _, slot, uid, minuten, spiele_n in paare:
        if elf[slot] is None and uid not in vergeben:
            elf[slot] = uid
            vergeben.add(uid)
            grund[slot] = {"art": "einsaetze", "minuten": int(minuten), "spiele": spiele_n,
                           "position": fm_position(meta[slot])}  # fmt: skip
    offen = {s: df[~df["uid"].astype(str).isin(vergeben)] for s, df in eigene.items() if elf[s] is None}
    for slot, uid in aufstellung(offen).items():
        elf[slot] = uid
        grund[slot] = {"art": "score" if uid else "keiner"}
    return elf, grund


PUNKT_FELDER = [
    "uid",
    "name",
    "club",
    "age",
    "value",
    "value_min",
    "value_max",
    "paar_gew",
    "liga_stufe",
    "eigen",
]


def punkte(df: pd.DataFrame, n_max: int = 600) -> list[dict]:
    """Schlanke Zeilen für den Preis-Leistungs-Chart (Score × Marktwert), beste zuerst, höchstens n_max."""
    return [
        {k: (str(r["uid"]) if k == "uid" else _wert(r.get(k))) for k in PUNKT_FELDER}
        for _, r in df.head(n_max).iterrows()
    ]


def fm_position(slot: dict) -> str | None:
    """Positionsbezeichnung des Slots wie in der Spalte "Pos." im FM27-Spielbildschirm, z. B. "OM (R)", "V (Z)"."""
    pos, x, y = slot.get("position"), slot["x"], slot["y"]
    seite = "R" if x > 60 else "L" if x < 40 else "Z"
    return {
        "TW": "TW", "IV": "V (Z)", "AV": f"V ({seite})", "FV": f"FV ({seite})", "DM": "DM", "ZM": "M (Z)",
        "OM": "OM (Z)", "ST": "ST (Z)", "FL": f"OM ({seite})" if y < 40 else f"M ({seite})",
    }.get(pos)  # fmt: skip


def einsaetze_je_spieler(ctx: Kontext) -> dict[str, pd.DataFrame]:
    """Erfasste, gespielte Spiele (Tabelle spieleinsaetze) je Spieler-UID; leer ohne DB oder ohne Erfassung."""
    if not ctx.db:
        return {}
    conn = common.connect(ctx.db_path)
    try:
        df = spiele.einsaetze(conn, ctx.save)
    finally:
        conn.close()
    if df.empty:
        return {}
    df = df[df["eingesetzt"] == 1]
    return {str(u): t for u, t in df.groupby("player_uid")}


def auf_position(zeilen: list[dict], label: str | None, info: dict[str, pd.DataFrame]) -> None:
    """Ergänzt je Spieler: Minuten/Spiele/Note auf der Slot-Position und erfasste Minuten insgesamt."""
    for z in zeilen:
        t = info.get(z["uid"])
        if t is None:
            z.update(erfasst_min=None, pos_min=None, pos_spiele=None, pos_note=None)
            continue
        m = t[t["position"] == label] if label else t.iloc[0:0]
        noten = m["note"].dropna()
        z.update(
            erfasst_min=int(t["minuten"].sum()), erfasst_spiele=len(t), pos_min=int(m["minuten"].sum()),
            pos_spiele=len(m), pos_note=round(float(noten.mean()), 2) if len(noten) else None,
        )  # fmt: skip


def plan(
    ctx: Kontext, formation: str, auswahl: dict[str, dict], f: Filter, aufstellung_nach: str = "score"
) -> dict:
    """Je Slot: eigene Rangliste, Verbesserungen gegenüber dem gesetzten Spieler, Datenlücken; dazu die Elf.

    aufstellung_nach: "score" = beste Elf nach Paar-Score, "einsaetze" = wie bisher gespielt (erfasste Spiele)."""
    if aufstellung_nach not in ("score", "einsaetze"):
        common.die(f"Unbekannte Aufstellung '{aufstellung_nach}' (score oder einsaetze).")
    filter_pruefen(ctx, f)
    form = (ctx.formationen.get("formationen") or {}).get(formation)
    if not form:
        common.die(f"Formation '{formation}' fehlt in config/formationen.yaml.")
    meta = formationen_meta(ctx)[formation]["slots"]
    bewertet, eigene = {}, {}
    for sn, s in meta.items():
        sel = auswahl.get(sn) or {}
        mit_n, ohne_n = sel.get("mit") or s["mit"], sel.get("ohne") or s["ohne"]
        for n, phase in ((mit_n, "mit"), (ohne_n, "ohne")):
            if n not in s["optionen"][phase]:
                common.die(f"Rolle '{n}' passt nicht zu Slot '{sn}' ({phase} Ball).")
        mit, ohne, own, cand = slot_bewerten(ctx, mit_n, ohne_n, f)
        bewertet[sn] = (mit_n, ohne_n, mit, ohne, own, cand)
        eigene[sn] = own
    info = einsaetze_je_spieler(ctx)
    if aufstellung_nach == "einsaetze":
        elf, gruende = aufstellung_einsaetze(eigene, meta, info)
    else:
        elf = aufstellung(eigene)
        gruende = {s: {"art": "score" if u else "keiner"} for s, u in elf.items()}
    slots = {}
    for sn, (mit_n, ohne_n, mit, ohne, own, cand) in bewertet.items():
        gesetzt = elf[sn]
        ref_row = own[own["uid"].astype(str) == gesetzt] if gesetzt else own.iloc[0:0]
        basis = float(ref_row["paar_gew"].iat[0]) if len(ref_row) else None
        besser = cand if basis is None else cand[cand["paar_gew"] > basis]
        top_own = own.head(f.top_eigene)
        if len(ref_row) and gesetzt not in set(top_own["uid"].astype(str)):
            top_own = pd.concat([ref_row, top_own])
        kand = _zeilen(ctx, besser.head(f.top_kandidaten), mit, ohne)
        for z in kand:
            z["delta"] = None if basis is None else _wert(z["paar_gew"] - basis)
        eig = _zeilen(ctx, top_own, mit, ohne)
        key_ergaenzen(ctx, eig + kand, mit_n, ohne_n)
        rm, ro = ctx.rk["rollen"][mit], ctx.rk["rollen"][ohne]
        slots[sn] = {
            "mit": mit_n, "ohne": ohne_n,
            "gewertet_als": {"mit": mit, "ohne": ohne},
            "verlaesslichkeit": {"mit": rm.get("verlaesslichkeit"), "ohne": ro.get("verlaesslichkeit")},
            "hinweise": [r["luecken"] for r in (rm, ro) if r.get("luecken")],
            "gesetzt": gesetzt, "gesetzt_grund": gruende.get(sn), "basis": _wert(basis),
            "eigene": eig, "n_eigene": len(own), "key": key_defs(ctx, mit_n, ohne_n),
            "ohne_wertung": ohne_wertung(ctx, mit, own, f), "verliehen": verliehen(ctx, mit),
            "verbesserungen": kand, "n_verbesserungen": len(besser), "n_kandidaten": len(cand),
            "luecken": slot_luecken(ctx, mit, ohne),
            "n_pool": {"mit": ctx.anker[rm["gruppe"]]["n_pool"], "ohne": ctx.anker[ro["gruppe"]]["n_pool"]},
            "punkte": {"kandidaten": punkte(cand), "eigene": punkte(own)},
        }  # fmt: skip
    for sn, sl in slots.items():
        sl["fm_position"] = fm_position(meta[sn])
        auf_position(sl["eigene"], sl["fm_position"], info)
    return {"formation": formation, "slots": slots, "elf": elf, "stand": ctx.stand,
            "einsaetze_erfasst": len(info), "aufstellung_nach": aufstellung_nach}  # fmt: skip
