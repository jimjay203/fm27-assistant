"""Spielerprofil für den Kaderplaner: Score-Aufschlüsselung, Statistiken, Attribute und Stammdaten.

Score-Aufschlüsselung wie rollen.rolle_bewerten: Statistik-Score 0/50/100 an den Ankern (Schlecht/OK/Gut) der
Positionsgruppe, Baustein = Mittel seiner Statistiken, Rolle = gewichtetes Mittel der Bausteine.
Perzentil der Statistiken: Anteil des Vergleichspools der Positionsgruppe (wie die Anker), den der Spieler
übertrifft; bei 'weniger ist besser' gespiegelt, also immer hoch = gut.
Attribute und Infofelder kommen aus der DB (Export-Snapshot des Spielers), nur was dort steht: exakte Werte oder
die Scouting-Spanne des Spiels (lo-hi). Live gibt es Attribute nur für eigene Spieler (siehe live.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b
import common
import per90
import planer
import rollen

# Anzeige der Statistiken: Gruppe -> [(interner Name, Bezeichnung)]. Nicht gelistete Statistiken: "Weitere".
STAT_GRUPPEN: dict[str, list[tuple[str, str]]] = {
    "Abschluss": [
        ("tore", "Tore"), ("npxg", "xG ohne Elfmeter"), ("xg", "xG"), ("schuesse", "Schüsse"),
        ("schuesse_aufs_tor", "Schüsse aufs Tor"), ("schussgenauigkeit_pct", "Schussgenauigkeit %"),
        ("konversionsrate_pct", "Chancenverwertung %"), ("xg_pro_schuss_avg", "xG pro Schuss"),
        ("schuesse_fern_p90", "Fernschüsse pro 90"), ("tore_fernschuss", "Fernschusstore"),
        ("elfer_tore", "Elfmetertore"), ("abseits", "Abseits"),
    ],
    "Kreation und Passspiel": [
        ("assists", "Vorlagen"), ("xa", "xA"), ("schluesselpaesse", "Schlüsselpässe"),
        ("entscheidende_paesse_spiel_p90", "Entscheidende Pässe (Spiel) pro 90"),
        ("grosschancen", "Großchancen kreiert"), ("progressive_paesse", "Progressive Pässe"),
        ("paesse_versucht", "Pässe versucht"), ("paesse_angekommen", "Pässe angekommen"),
        ("passquote_pct", "Passquote %"), ("flanken_versucht", "Flanken versucht"),
        ("flanken_angekommen", "Flanken angekommen"), ("flankenquote_pct", "Flankenquote %"),
        ("flanken_spiel_versucht", "Flanken aus dem Spiel versucht"),
        ("flanken_spiel_angekommen", "Flanken aus dem Spiel angekommen"),
        ("flankenquote_spiel_pct", "Flankenquote aus dem Spiel %"), ("dribblings", "Dribblings"),
        ("gefoult", "Gefoult worden"), ("freistoesse", "Freistöße"),
    ],
    "Defensive": [
        ("tacklings_versucht", "Tacklings versucht"), ("tacklings_gewonnen", "Tacklings gewonnen"),
        ("tackling_pct", "Tacklingquote %"), ("tacklings_entscheidend", "Entscheidende Tacklings"),
        ("abgefangen", "Abgefangene Bälle"), ("klaerungen", "Klärungen"), ("geblockt", "Geblockt"),
        ("schuesse_geblockt", "Schüsse geblockt"), ("pressing_versucht", "Pressing versucht"),
        ("pressing_erfolgreich", "Pressing erfolgreich"), ("pressingquote_pct", "Pressingquote %"),
        ("ballgewinne", "Ballgewinne"), ("ballverluste", "Ballverluste"),
        ("kopfbaelle_versucht", "Kopfballduelle"), ("kopfbaelle_gewonnen", "Kopfballduelle gewonnen"),
        ("kopfballduelle_gewonnen_pct", "Kopfballquote %"),
        ("entscheidende_kopfbaelle_p90", "Entscheidende Kopfbälle pro 90"),
        ("fehler_torfolge", "Fehler vor Gegentor"), ("fouls", "Fouls"), ("gelb", "Gelbe Karten"),
        ("rot", "Rote Karten"),
    ],
    "Physis": [("distanz_km", "Laufdistanz km"), ("sprints_p90", "Sprints pro 90")],
    "Torwart": [
        ("gegentore_n", "Gegentore"), ("zu_null_n", "Zu-null-Spiele"), ("tw_gehalten", "Schüsse gehalten"),
        ("tw_pariert", "Schüsse pariert"), ("tw_abgelenkt", "Schüsse abgelenkt"), ("par_pct", "Paraden %"),
        ("xsv_pct", "xSv %"), ("xgp", "xG verhindert"), ("elfer_pariert", "Elfmeter pariert"),
    ],
    "Allgemein": [
        ("wertung_avg", "Durchschnittsnote"), ("spieler_des_spiels", "Spieler des Spiels"),
        ("einsaetze_start_n", "Startelf-Einsätze"), ("einsaetze_ein_n", "Einwechslungen"),
        ("siege_n", "Siege"), ("unentschieden_n", "Unentschieden"), ("niederlagen_n", "Niederlagen"),
    ],
}  # fmt: skip
NIEDRIG_BESSER = {"abseits", "ballverluste", "fehler_torfolge", "fouls", "gelb", "rot", "gegentore_n",
                  "niederlagen_n"}  # fmt: skip
# Nur Anzeige, kein Perzentil (Mannschafts- oder Kontextwerte)
OHNE_PERZENTIL = {"siege_n", "unentschieden_n", "niederlagen_n", "einsaetze_start_n", "einsaetze_ein_n",
                  "zu_null_n", "spieler_des_spiels"}  # fmt: skip

# Attributgruppen wie im Spielerprofil des Spiels
ATTRIBUT_GRUPPEN: dict[str, list[str]] = {
    "Technik": ["Abschluss", "Ballannahme", "Deckung", "Dribbling", "Ecken", "Elfmeter", "Flanken",
                "Freistöße", "Kopfballtechnik", "Passen", "Tackling", "Technik", "Weite Einwürfe",
                "Weitschüsse"],
    "Mental": ["Aggressivität", "Antizipation", "Einsatzfreude", "Entscheidungen", "Führungsqualitäten",
               "Konzentration", "Kreativität", "Mut", "Nervenstärke", "Ohne Ball", "Stellungsspiel",
               "Teamwork", "Übersicht", "Zielstrebigkeit"],
    "Physis": ["Antritt", "Ausdauer", "Balance", "Beweglichkeit", "Grundfitness", "Kraft", "Schnelligkeit",
               "Sprunghöhe"],
    "Torwart": ["Abschlag", "Abwurf", "Eins gegen Eins", "Exzentrizität", "Fausten", "Halten",
                "Herauslaufen (Tendenz)", "Hohe Bälle", "Kommunikation", "Reflexe", "Strafraumkontrolle"],
}  # fmt: skip

INFO_LABELS = {
    "nation": "Nation", "geburtsland": "Geburtsland", "groesse": "Größe", "fuss_links": "Linker Fuß",
    "fuss_rechts": "Rechter Fuß", "idealpos": "Idealposition", "persoenlichkeit": "Persönlichkeit",
    "medienumgang": "Medienumgang", "rolle": "Einsatzzeiten", "rolle_tatsaechlich": "Tatsächliche Einsatzzeiten",
    "zufriedenheit": "Zufriedenheit", "gesamtzufriedenheit": "Gesamtzufriedenheit",
    "zufriedenheit_einsaetze": "Zufriedenheit Einsätze", "vertragsart": "Vertragsart",
    "vertragsbeginn": "Vertragsbeginn", "vertragsstatus": "Vertragsstatus",
    "abloeseforderung": "Ablöseforderung", "ausgeliehen_von": "Ausgeliehen von",
    "eigengewaechs": "Eigengewächs", "hierarchie": "Hierarchie", "verletzung": "Verletzung",
    "verletzt_am": "Verletzt am", "ausfallszeit": "Ausfallzeit", "verletzungsrisiko": "Verletzungsrisiko",
    "verletzungsanfaelligkeit": "Verletzungsanfälligkeit", "spielbelastung": "Spielbelastung",
    "trainingsbelastung": "Trainingsbelastung",
}  # fmt: skip

KERN = ["uid", "name", "club", "league", "club_country", "position", "age", "birthdate", "minutes",
        "value", "value_min", "value_max", "wage", "wage_min", "wage_max", "contract_end", "loan_start",
        "loan_end", "eigen", "datenbasis", "in_suche", "quelle"]  # fmt: skip
NICHT_STATS = set(per90.CORE_COLS) | set(KERN) | {
    "snapshot_id", "view_type", "own", "team", "uid", "ausfallszeit_tage_n", "verpasste_spiele_n",
    "team_tore_n", "team_gegentore_n", "elfer", "elfer_gesamt",
}  # fmt: skip

_w = planer._wert


def _zeile(ctx: planer.Kontext, uid: str) -> pd.DataFrame:
    hit = ctx.df[ctx.df["uid"].astype(str) == str(uid)]
    if hit.empty:
        common.die(f"Spieler '{uid}' ist nicht in den geladenen Daten.")
    return hit.iloc[[0]]


def _pool(ctx: planer.Kontext, gruppe: str) -> pd.DataFrame:
    if gruppe not in ctx.pools:
        prof = {"positionen": ctx.rk["positionsgruppen"][gruppe]}
        ctx.pools[gruppe] = b.anker_pool(ctx.df, prof, ctx.defaults, ctx.lg, ctx.pool_min_stufe)
    return ctx.pools[gruppe]


def ist_zaehlwert(stat: str) -> bool:
    return not stat.endswith(per90.NOT_NORMALIZED)


def _pro90(df: pd.DataFrame, stat: str) -> pd.Series:
    return b.stat_values(df, {"stat": stat, "art": "p90" if ist_zaehlwert(stat) else "pct"})


# --------------------------------------------------------------------------- Scores


def score_aufschluesselung(
    ctx: planer.Kontext, sub: pd.DataFrame, rollen_namen: dict
) -> list[dict]:
    """Je Rolle (mit/ohne): Score, vs_top, Bausteine mit ihren Statistiken. Werte als Liste je Zeile von `sub`."""

    def liste(s) -> list:
        return [_w(x) for x in np.asarray(s, dtype=float)]

    out = []
    for phase, anzeige in rollen_namen.items():
        name = rollen.aufloesen(anzeige, ctx.rk)
        r = ctx.rk["rollen"][name]
        g = r["gruppe"]
        anker_g, ref_g = ctx.anker[g], ctx.ref.get(g, {})
        score, top, detail = rollen.rolle_bewerten(sub, name, ctx.rk, anker_g, ref_g)
        fehlend = ctx.luecken.get(g, {}).get("statistiken", {})
        bausteine = []
        for bn, gew in r["bausteine"].items():
            stats = []
            for s in ctx.rk["bausteine"][bn]["stats"]:
                st = s["stat"]
                a = anker_g["stats"].get(st)
                label = next((lb for grp in STAT_GRUPPEN.values() for k, lb in grp if k == st), st)
                e = {
                    "stat": st,
                    "label": label,
                    "art": s["art"],
                    "niedrig": s.get("richtung") == "niedrig",
                }
                if not a:
                    e["fehlt"] = fehlend.get(st, "kein Anker")
                    stats.append(e)
                    continue
                v = b.stat_values(sub, a)
                rf = ref_g.get(st)
                e.update(
                    schlecht=_w(a["schlecht"]), ok=_w(a["ok"]), gut=_w(a["gut"]), wert=liste(v),
                    score=liste(b.stat_scores(v, a)),
                    vs_top=liste(b.prozent_im_referenz(rf, v, a["schlecht"] > a["gut"])) if rf is not None
                    else [None] * len(sub),
                )  # fmt: skip
                stats.append(e)
            bausteine.append({
                "baustein": bn, "label": ctx.rk["bausteine"][bn].get("name", bn), "gewicht": float(gew),
                "score": liste(detail[bn]) if bn in detail else [None] * len(sub), "stats": stats,
            })  # fmt: skip
        out.append({
            "phase": phase, "rolle": anzeige, "gewertet_als": name, "gruppe": g,
            "verlaesslichkeit": r.get("verlaesslichkeit"), "luecken": r.get("luecken"),
            "begruendung": r.get("begruendung"), "score": liste(score), "vs_top": liste(top),
            "bausteine": bausteine,
        })  # fmt: skip
    return out


# --------------------------------------------------------------------------- Statistiken


def statistiken(ctx: planer.Kontext, row: pd.DataFrame, gruppe: str) -> list[dict]:
    """Alle Statistiken des Spielers: Gesamt, pro 90 (Zählwerte) und Perzentil im Pool der Positionsgruppe."""
    pool = _pool(ctx, gruppe)
    r = row.iloc[0]
    bekannt = {k for grp in STAT_GRUPPEN.values() for k, _ in grp}
    weitere = sorted(
        c for c in row.columns
        if c not in bekannt and c not in NICHT_STATS and pd.api.types.is_numeric_dtype(row[c])
    )  # fmt: skip
    ist_tw = any(t == "GK" for t, _ in b.parse_positions(r["position"]))
    gruppen = [(g, e) for g, e in STAT_GRUPPEN.items() if ist_tw or g != "Torwart"]
    gruppen.append(("Weitere", [(c, c) for c in weitere]))
    out = []
    for gname, eintraege in gruppen:
        zeilen = []
        for st, label in eintraege:
            if st not in row or pd.isna(r[st]):
                continue
            z = {"stat": st, "label": label, "gesamt": _w(r[st]), "pro90": None, "perzentil": None,
                 "niedrig": st in NIEDRIG_BESSER}  # fmt: skip
            v = _pro90(row, st).iat[0]
            if ist_zaehlwert(st):
                z["pro90"] = _w(v)
            if st not in OHNE_PERZENTIL and st in pool and not pd.isna(v):
                ref = np.sort(_pro90(pool, st).dropna().to_numpy())
                if len(ref):
                    z["perzentil"] = _w(
                        float(b.prozent_im_referenz(ref, [v], st in NIEDRIG_BESSER)[0])
                    )
                    z["n_pool"] = len(ref)
            zeilen.append(z)
        if zeilen:
            out.append({"gruppe": gname, "stats": zeilen})
    return out


# --------------------------------------------------------------------------- Attribute und Infofelder


def _snapshot_fuer(conn, save: str, uid: str, bevorzugt: int | None) -> tuple[int, str, str] | None:
    """Snapshot mit Attributen des Spielers: der geladene, sonst der neueste mit Attributen."""
    q = (
        "SELECT s.id, s.ingame_date, s.view_type FROM snapshots s "
        "JOIN player_attributes a ON a.snapshot_id = s.id "
        "WHERE s.save = ? AND a.player_uid = ? GROUP BY s.id "
        "ORDER BY (s.id = ?) DESC, s.ingame_date DESC, s.id DESC LIMIT 1"
    )
    r = conn.execute(q, (save, str(uid), bevorzugt or -1)).fetchone()
    return (int(r[0]), r[1], r[2]) if r else None


def attribute_und_info(ctx: planer.Kontext, row: pd.DataFrame) -> dict:
    r = row.iloc[0]
    if not ctx.db:
        return {"grund": "Keine Datenbank angebunden.", "gruppen": [], "info": []}
    snap_id = r.get("snapshot_id")
    bevorzugt = None if snap_id is None or pd.isna(snap_id) else int(snap_id)
    conn = common.connect(ctx.db_path)
    try:
        snap = _snapshot_fuer(conn, ctx.save, r["uid"], bevorzugt)
        info_snap = bevorzugt or (snap[0] if snap else None)
        info = []
        if info_snap is not None:
            for feld, text in conn.execute(
                "SELECT field, text FROM player_info WHERE snapshot_id = ? AND player_uid = ?",
                (info_snap, str(r["uid"])),
            ):
                if feld in INFO_LABELS and text:
                    info.append({"feld": feld, "label": INFO_LABELS[feld], "text": text})
            info.sort(key=lambda e: list(INFO_LABELS).index(e["feld"]))
        if not snap:
            return {
                "grund": "Keine Attribute in der DB: Spieler steht in keinem Kader- oder Suche-Export "
                "(live gibt es Attribute nur für eigene Spieler).",
                "gruppen": [], "info": info,
            }  # fmt: skip
        werte = {
            a: {"wert": _w(v), "lo": _w(lo), "hi": _w(hi), "verdeckt": bool(m)}
            for a, v, m, lo, hi in conn.execute(
                "SELECT attribute, value, masked, lo, hi FROM player_attributes "
                "WHERE snapshot_id = ? AND player_uid = ?",
                (snap[0], str(r["uid"])),
            )
        }
    finally:
        conn.close()
    ist_tw = any(t == "GK" for t, _ in b.parse_positions(r["position"]))
    gruppen = []
    for gname, namen in ATTRIBUT_GRUPPEN.items():
        if gname == "Torwart" and not ist_tw:
            continue
        eintraege = [{"name": n, **werte[n]} for n in namen if n in werte]
        if eintraege:
            gruppen.append({"gruppe": gname, "attribute": eintraege})
    bekannt = {n for ns in ATTRIBUT_GRUPPEN.values() for n in ns}
    rest = [{"name": n, **w} for n, w in sorted(werte.items()) if n not in bekannt]
    if rest:
        gruppen.append({"gruppe": "Weitere", "attribute": rest})
    n_spanne = sum(1 for w in werte.values() if w["wert"] is None and w["lo"] is not None)
    return {
        "quelle": {"datum": snap[1], "ansicht": snap[2]}, "gruppen": gruppen, "info": info,
        "n_exakt": sum(1 for w in werte.values() if w["wert"] is not None), "n_spanne": n_spanne,
    }  # fmt: skip


def chart_daten(ctx: planer.Kontext, sub: pd.DataFrame, aufschl: list[dict]) -> list[dict]:
    """Je Statistik der beiden Rollen (einmal, mit Anker): Perzentil im Pool der Positionsgruppe der Rolle.

    Reihenfolge wie in den Rollen (mit Ball, dann ohne Ball; je Baustein). Perzentil: hoch = gut, auch bei
    'weniger ist besser'. Werte je Zeile von `sub` (Spieler, ggf. Vergleich)."""
    out, gesehen = [], set()
    for r in aufschl:
        pool = _pool(ctx, r["gruppe"])
        for bs in r["bausteine"]:
            for st in bs["stats"]:
                if st.get("fehlt") or st["stat"] in gesehen:
                    continue
                gesehen.add(st["stat"])
                spec = {"stat": st["stat"], "art": st["art"]}
                ref = np.sort(b.stat_values(pool, spec).dropna().to_numpy())
                v = b.stat_values(sub, spec).to_numpy(dtype=float)
                pz = b.prozent_im_referenz(ref, v, st["niedrig"]) if len(ref) else [np.nan] * len(v)
                out.append({
                    "stat": st["stat"], "label": st["label"], "baustein": bs["label"], "phase": r["phase"],
                    "art": st["art"], "niedrig": st["niedrig"], "n_pool": len(ref),
                    "wert": [_w(x) for x in v], "perzentil": [_w(float(x)) for x in pz],
                })  # fmt: skip
    return out


# --------------------------------------------------------------------------- Profil


def profil(
    ctx: planer.Kontext, uid: str, mit: str, ohne: str, vergleich: str | None = None,
    gewichtung: str | None = None,
) -> dict:  # fmt: skip
    """Profil eines Spielers für das Rollenpaar; `vergleich` = uid eines zweiten Spielers (z. B. der gesetzte).

    `gewichtung` wie im Filter des Plans (None = Schema der Positionsgruppe, 'aus' = ohne Liga-Gewicht)."""
    for n in (mit, ohne):
        rollen_name = rollen.aufloesen(n, ctx.rk)
        if rollen_name not in ctx.rk["rollen"]:
            common.die(f"Rolle '{n}' fehlt in config/rollen_kpis.yaml.")
    row = _zeile(ctx, uid)
    sub = row
    if vergleich and str(vergleich) != str(uid):
        sub = pd.concat([row, _zeile(ctx, vergleich)])
    sub = sub.reset_index(drop=True)
    paar = rollen.paar_bewerten(
        sub, rollen.aufloesen(mit, ctx.rk), rollen.aufloesen(ohne, ctx.rk), ctx.rk, ctx.anker, ctx.ref,
        ctx.defaults,
    )  # fmt: skip
    gruppe = ctx.rk["rollen"][rollen.aufloesen(mit, ctx.rk)]["gruppe"]
    schema = gewichtung or ctx.rk["gewichtung_je_gruppe"].get(gruppe)
    spieler = []
    for i in range(len(sub)):
        r = sub.iloc[i]
        lgw = ctx.lg.gewicht(r.get("league"), schema) if schema != "aus" else 1.0
        p = paar["paar"].iat[i]
        spieler.append({
            **{k: _w(r.get(k)) for k in KERN}, "uid": str(r["uid"]),
            "liga_stufe": ctx.lg.stufe(r.get("league")), "liga_gewicht": _w(lgw),
            "mit": _w(paar["mit"].iat[i]), "ohne": _w(paar["ohne"].iat[i]), "paar": _w(p),
            "paar_gew": _w(p * lgw) if lgw is not None and not pd.isna(p) else None,
            "vs_top": _w(paar["vs_top"].iat[i]),
        })  # fmt: skip
    aufschl = score_aufschluesselung(ctx, sub, {"mit": mit, "ohne": ohne})
    return {
        "spieler": spieler[0],
        "vergleich": spieler[1] if len(spieler) > 1 else None,
        "rollen": aufschl,
        "chart": chart_daten(ctx, sub, aufschl),
        "statistiken": statistiken(ctx, row, gruppe),
        "attribute": attribute_und_info(ctx, row),
        "pool": {"gruppe": gruppe, "n": len(_pool(ctx, gruppe)), "min_stufe": ctx.pool_min_stufe},
    }
