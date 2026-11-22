"""Kaderplaner: beste eigene Spieler je Slot einer Formation und Verbesserungen aus der Spielersuche.

Fachlogik ohne Web-Bezug (die Oberfläche ist scripts/webapp.py). Bewertet wird mit dem Rollen-Score aus
scripts/rollen.py (Rollenpaar mit/ohne Ball, Anker = Perzentile 25/55/90 des Vergleichspools, Rollen-Zuordnung
ungeprüft, siehe wissen/rollen-kpis.md). Formationen: config/formationen.yaml.

Datenquellen:
- db (Standard): letzter Kader-Snapshot = eigene Spieler, letzter Suche-Snapshot = Kandidaten. Der Vergleichspool
  der Anker ist die Vereinigung beider, also so breit wie die letzte Spielersuche.
- live: FMMT-27-Server (alle Spieler des Saves). `in_suche` markiert Spieler aus dem letzten Suche-Snapshot.
"""

from __future__ import annotations

import math
import sys
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
import sellkeep

SPIELER_FELDER = [
    "uid", "name", "club", "league", "liga_stufe", "position", "age", "minutes", "eigen", "datenbasis",
    "mit", "ohne", "paar", "liga_gewicht", "paar_gew", "vs_top",
    "value", "value_min", "value_max", "wage", "wage_min", "wage_max", "contract_end", "loan_end",
]  # fmt: skip


# --------------------------------------------------------------------------- Daten


def daten_db(conn, save: str, verein: str | None = None) -> pd.DataFrame:
    """Eigene Spieler (letzter Kader-Snapshot) + Kandidaten (letzte Spielersuche) als ein DataFrame."""
    kader = per90.letzter_snapshot(conn, save, "kader")
    suche = per90.letzter_snapshot(conn, save, "suche")
    if not kader:
        common.die(
            f"Kein Kader-Snapshot für Save '{save}'. Kader-Export importieren (scripts/import.py)."
        )
    ids = [kader[0]] + ([suche[0]] if suche else [])
    players, _ = per90.load_wide(conn, save, snapshot_ids=ids)
    players = players.reset_index(drop=True)
    ist_kader = players["snapshot_id"] == kader[0]
    if verein is None:
        verein = players.loc[ist_kader, "club"].mode().iat[0]
    status = sellkeep.squad_status(players, conn, verein)
    # Eigene Spieler nur aus dem Kader-Snapshot; dort stehen auch Verliehene (Status leihe_aus).
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
        "datum": max(d for d in (kader[1], suche[1] if suche else None) if d),
        "kader_datum": kader[1],
        "suche_datum": suche[1] if suche else None,
    }
    return players


def daten_live(url: str, conn, save: str, config_dir=None) -> pd.DataFrame:
    """Alle Spieler live vom FMMT-27-Server; `in_suche` = im letzten Suche-Snapshot der DB."""
    df = b.load_live(
        url,
        common.load_yaml("live_spalten.yaml", config_dir),
        common.load_yaml("spalten.yaml", config_dir).get("abgeleitet") or {},
    )
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
    df.attrs["stand"] = {
        "quelle": "live",
        "verein": None,
        "datum": df.attrs.get("date"),
        "suche_datum": suche[1] if suche else None,
        "suche_abgleich": int(df["in_suche"].sum()),
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
) -> Kontext:
    """Anker und Topclub-Referenz für alle Rollen einmal je Datenladung berechnen."""
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
        n_eigene=int(df["own"].sum()) if "own" in df else 0,
        n_suche=int(df["in_suche"].sum()) if "in_suche" in df else 0,
        pool_min_stufe=pool_min_stufe,
        anker_min_n=anker_min_n,
        topclubs=clubs,
    )
    return Kontext(
        df=df, rk=rk, lg=lg, defaults=defaults, formationen=formationen,
        slots_taktik=slots_taktik or {}, specs=specs, anker=anker, ref=ref, clubs=clubs,
        stand=stand, luecken=luecken, pool_min_stufe=pool_min_stufe,
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
                "position": s.get("position"), "x": s["x"], "y": s["y"], "optionen": opt,
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
        z["bausteine"] = {
            "mit": {k: _wert(v) for k, v in d_m.loc[idx].dropna().items()},
            "ohne": {k: _wert(v) for k, v in d_o.loc[idx].dropna().items()},
        }
        rows.append(z)
    return rows


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
    """Eigene Spieler der Positionsgruppe, die keinen Score haben, mit Grund."""
    rules = ctx.rk["positionsgruppen"][ctx.rk["rollen"][mit]["gruppe"]]
    df = ctx.df
    sub = df[df["own"] & df["position"].map(lambda p: b.position_ok(p, rules))]
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
                    "minutes": _wert(mins), "eigen": _wert(r.get("eigen")), "grund": grund})  # fmt: skip
    return out


def aufstellung(eigene: dict[str, pd.DataFrame]) -> dict[str, str | None]:
    """Beste eigene Elf ohne Doppelbesetzung: greedy über (Slot, Spieler) absteigend nach paar_gew.

    Verliehene Spieler (eigen = leihe_aus) werden nicht gesetzt."""
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


def plan(ctx: Kontext, formation: str, auswahl: dict[str, dict], f: Filter) -> dict:
    """Je Slot: eigene Rangliste, Verbesserungen gegenüber dem gesetzten Spieler, Datenlücken; dazu die Elf."""
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
    elf = aufstellung(eigene)
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
        rm, ro = ctx.rk["rollen"][mit], ctx.rk["rollen"][ohne]
        slots[sn] = {
            "mit": mit_n, "ohne": ohne_n,
            "gewertet_als": {"mit": mit, "ohne": ohne},
            "verlaesslichkeit": {"mit": rm.get("verlaesslichkeit"), "ohne": ro.get("verlaesslichkeit")},
            "hinweise": [r["luecken"] for r in (rm, ro) if r.get("luecken")],
            "gesetzt": gesetzt, "basis": _wert(basis),
            "eigene": _zeilen(ctx, top_own, mit, ohne), "n_eigene": len(own),
            "ohne_wertung": ohne_wertung(ctx, mit, own, f),
            "verbesserungen": kand, "n_verbesserungen": len(besser), "n_kandidaten": len(cand),
            "luecken": slot_luecken(ctx, mit, ohne),
            "n_pool": {"mit": ctx.anker[rm["gruppe"]]["n_pool"], "ohne": ctx.anker[ro["gruppe"]]["n_pool"]},
        }  # fmt: skip
    return {"formation": formation, "slots": slots, "elf": elf, "stand": ctx.stand}
