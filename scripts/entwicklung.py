"""Entwicklung der eigenen Spieler: Attribut-Verlauf, Per-90 je Zeitraum, Saisonvergleich, Noten je Spiel.

Quellen
- Attribute: Kader-Exporte (exakt) und Live-Stände (Tabelle attribut_verlauf, beim Laden über FMMT-27
  mitgeschrieben, ein Stand je In-Game-Tag). Am selben Tag gilt der Export.
- Statistiken: Kader-Exporte. Dort kumuliert je Saison (Saisongrenze config/saison.yaml), ein Zeitraum ist also die
  Differenz zweier Exporte derselben Saison. Zählwerte pro 90, Quoten aus Zähler/Nenner (config/spalten.yaml,
  abgeleitet), übrige Raten minuten- bzw. spielgewichtet. Zeiträume unter MIN_ZEITRAUM Minuten werden mit dem
  folgenden zusammengelegt.
- Noten: SpielLogger (Tabelle spieleinsaetze), Note je Spiel und gleitender Schnitt.
Zuwachs aus Training und Spielen lässt sich aus den Daten nicht trennen; die Seite zeigt ihn neben den Minuten.

Aufruf:  uv run python scripts/entwicklung.py --save werder [--von JJJJ-MM-TT] [--bis JJJJ-MM-TT] [--zeige NAME]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b
import common
import namen
import per90
import planer
import rollen_attr
import spiele
import spielerprofil

OHNE_TEAM = "ohne Teamangabe"
MIN_ZEITRAUM = 270  # Minuten (etwa 3 Spiele)
GLEITEND = 5  # Spiele im gleitenden Notenschnitt
_w = planer._wert


# --------------------------------------------------------------------------- Daten


def attribut_verlauf(conn, save: str, uids=None) -> pd.DataFrame:
    """[uid, datum, quelle (export|live), attribute, value]; je uid/Attribut/Tag ein Wert, Export vor Live."""
    q_export = (
        "SELECT a.player_uid AS uid, s.ingame_date AS datum, 'export' AS quelle, a.attribute, a.value "
        "FROM player_attributes a JOIN snapshots s ON s.id = a.snapshot_id "
        "WHERE s.save = ? AND s.view_type = 'kader' AND a.value IS NOT NULL"
    )
    q_live = (
        "SELECT player_uid AS uid, datum, 'live' AS quelle, attribute, value FROM attribut_verlauf "
        "WHERE save = ? AND value IS NOT NULL"
    )
    df = pd.concat(
        [pd.read_sql_query(q, conn, params=(save,)) for q in (q_export, q_live)], ignore_index=True
    )
    df["uid"] = df["uid"].astype(str)
    if uids is not None:
        df = df[df["uid"].isin({str(u) for u in uids})]
    df = df.assign(_live=(df["quelle"] == "live").astype(int))
    df = df.sort_values(["uid", "attribute", "datum", "_live"])
    df = df.drop_duplicates(["uid", "attribute", "datum"], keep="first").drop(columns="_live")
    return df.reset_index(drop=True)


def _quelle_je_tag(verlauf: pd.DataFrame) -> pd.Series:
    return verlauf.groupby("datum")["quelle"].agg(lambda s: "export" if (s == "export").any() else "live")


def stichtage(verlauf: pd.DataFrame) -> list[dict]:
    """Alle Tage mit Attributen: [{datum, quelle}], quelle = export, wenn an dem Tag ein Export vorliegt."""
    if verlauf.empty:
        return []
    q = _quelle_je_tag(verlauf)
    return [{"datum": d, "quelle": q[d]} for d in sorted(q.index)]


def kader_stats(conn, save: str, grenze: str = "07-01") -> pd.DataFrame:
    """Je Spieler und Kader-Export: uid, datum, saison, minutes und alle Statistiken (kumuliert je Saison)."""
    p = pd.read_sql_query(
        "SELECT p.snapshot_id, p.player_uid AS uid, s.ingame_date AS datum, p.minutes FROM players p "
        "JOIN snapshots s ON s.id = p.snapshot_id WHERE s.save = ? AND s.view_type = 'kader'",
        conn, params=(save,),
    )  # fmt: skip
    if p.empty:
        return p.assign(saison=None)
    st = pd.read_sql_query(
        "SELECT x.snapshot_id, x.player_uid AS uid, x.stat, x.value FROM player_stats x "
        "JOIN snapshots s ON s.id = x.snapshot_id WHERE s.save = ? AND s.view_type = 'kader'",
        conn, params=(save,),
    )  # fmt: skip
    if not st.empty:
        breit = st.pivot_table(
            index=["snapshot_id", "uid"], columns="stat", values="value", aggfunc="last"
        )
        p = p.merge(breit.reset_index(), on=["snapshot_id", "uid"], how="left")
    p["uid"] = p["uid"].astype(str)
    p["saison"] = p["datum"].map(lambda d: per90.saison_von(d, grenze))
    p = p.sort_values(["uid", "datum", "snapshot_id"])
    return p.drop_duplicates(["uid", "datum"], keep="last").reset_index(drop=True)


# --------------------------------------------------------------------------- Rechnen


def _breit(verlauf_uid: pd.DataFrame) -> pd.DataFrame:
    """Attribute eines Spielers: Zeilen = Datum, Spalten = Attribut, Lücken mit dem letzten Stand gefüllt."""
    w = verlauf_uid.pivot_table(index="datum", columns="attribute", values="value", aggfunc="last")
    return w.sort_index().ffill()


def start_ende(breit: pd.DataFrame, von: str | None, bis: str | None):
    """(Stand am Anfang, Stand am Ende) als Series mit .name = Datum; Anfang = letzter Stand bis `von`, sonst der
    erste danach (Spieler später dazugekommen). None, wenn bis `bis` nichts vorliegt."""
    w = breit[breit.index <= bis] if bis else breit
    if w.empty:
        return None
    vor = w[w.index <= von] if von else w.iloc[:1]
    return (vor.iloc[-1] if len(vor) else w.iloc[0]), w.iloc[-1]


def minuten_zwischen(ks: pd.DataFrame, von: str | None, bis: str | None, grenze: str = "07-01") -> float | None:
    """Minuten eines Spielers zwischen zwei Tagen aus den kumulierten Saisonwerten der Kader-Exporte."""
    t = ks[ks["datum"] <= bis] if bis else ks
    t = t[t["minutes"].notna()]
    if t.empty:
        return None
    s_von = per90.saison_von(von, grenze) if von else None
    summe = 0.0
    for saison, g in t.groupby("saison"):
        if s_von and saison < s_von:
            continue
        basis = 0.0
        if von and saison == s_von:
            vor = g[g["datum"] <= von]
            basis = float(vor["minutes"].iloc[-1]) if len(vor) else 0.0
        summe += max(0.0, float(g["minutes"].iloc[-1]) - basis)
    return summe


def _art(stat: str, ableit: dict) -> str:
    """quote (Zähler/Nenner), anzahl (_n, absolut), rate (_pct/_avg/_p90 gewichtet), p90 (Zählwert pro 90)."""
    if stat in ableit:
        return "quote"
    if stat.endswith("_n"):
        return "anzahl"
    if stat.endswith(per90.RATEN):
        return "rate"
    return "p90"


def zeitraum_werte(vorher, nachher, stats: list[str], ableit: dict) -> dict[str, float | None]:
    """Werte eines Zeitraums aus zwei kumulierten Ständen derselben Saison (`vorher` None = Saisonbeginn)."""

    def wert(r, c):
        if r is None:
            return 0.0
        v = r.get(c)
        return None if v is None or pd.isna(v) else float(v)

    def diff(c):
        a, z = wert(vorher, c), wert(nachher, c)
        return None if a is None or z is None else z - a

    def spiele_bis(r):
        return (wert(r, "einsaetze_start_n") or 0.0) + (wert(r, "einsaetze_ein_n") or 0.0)

    dm = diff("minutes")
    ma = wert(vorher, "minutes") or 0.0
    ga, gz = spiele_bis(vorher), spiele_bis(nachher)
    out: dict[str, float | None] = {}
    for st in stats:
        art, v = _art(st, ableit), None
        a, z = wert(vorher, st), wert(nachher, st)
        if art == "quote":
            dz, dn = diff(ableit[st][0]), diff(ableit[st][1])
            v = dz / dn * 100 if dz is not None and dn else None
        elif art == "anzahl":
            v = diff(st)
        elif art == "rate":
            if z is None:
                v = None
            elif st.endswith("_avg"):  # z. B. Durchschnittsnote: je Spiel gewichtet
                v = z if not ga or a is None else (z * gz - a * ga) / (gz - ga) if gz > ga else None
            elif dm and dm > 0:
                v = z if not ma or a is None else (z * (ma + dm) - a * ma) / dm
        else:
            d = diff(st)
            v = d / dm * 90 if d is not None and dm and dm > 0 else None
        out[st] = v
    return out


def perioden(
    ks: pd.DataFrame, stats: list[str], ableit: dict, grenze: str = "07-01",
    min_zeitraum: float = MIN_ZEITRAUM,
) -> list[dict]:  # fmt: skip
    """Zeiträume zwischen aufeinanderfolgenden Kader-Exporten je Saison; kurze werden zusammengelegt, der letzte
    Zeitraum einer Saison bleibt auch unter `min_zeitraum` stehen."""
    out = []
    for saison, g in ks.groupby("saison", sort=True):
        g = g[g["minutes"].notna()].sort_values("datum")
        vorher = None
        for i, (_, r) in enumerate(g.iterrows()):
            dm = float(r["minutes"]) - (float(vorher["minutes"]) if vorher is not None else 0.0)
            if dm <= 0 or (dm < min_zeitraum and i < len(g) - 1):
                continue  # kein Spiel oder zu kurz: mit dem nächsten Zeitraum zusammenlegen
            out.append({
                "saison": saison, "von": vorher["datum"] if vorher is not None else f"{saison[:4]}-{grenze}",
                "bis": r["datum"], "minuten": dm, "werte": zeitraum_werte(vorher, r, stats, ableit),
            })  # fmt: skip
            vorher = r
    return out


def slot_von(name: str, slots_taktik: dict) -> str | None:
    """Slot aus taktik_slots.yaml, in dessen stamm-Liste der Spieler am weitesten vorne steht."""
    best = None
    for sn, s in (slots_taktik or {}).items():
        for i, z in enumerate(s.get("stamm") or []):
            if namen.passt(name, z):
                if best is None or i < best[1]:
                    best = (sn, i)
                break
    return best[0] if best else None


def key_attribute(ctx, slot: str | None) -> list[str]:
    """Key-Attribute der Rollen des Slots (mit und ohne Ball, config/rollen_attribute.yaml), wie rollen.py."""
    s = (ctx.slots_taktik or {}).get(slot) or {}
    if not s.get("mit") or not s.get("ohne"):
        return []
    d = planer.key_defs(ctx, s["mit"], s["ohne"])
    return list(dict.fromkeys([*d["mit"]["key"], *d["ohne"]["key"]]))


def _ist_tw(position) -> bool:
    return any(t == "GK" for t, _ in b.parse_positions(position))


def _relevant(spalten, ist_tw: bool) -> list[str]:
    tw = set(spielerprofil.ATTRIBUT_GRUPPEN["Torwart"])
    return [a for a in spalten if ist_tw or a not in tw]


def team_von(ctx, r) -> str | None:
    """Team eines eigenen Spielers: nur live (FMMT-Reader); die Exporte haben kein Team-Feld (dort None).
    Profis = "Senior Team"; ohne Angabe des Readers: team_ohne_liste aus config/live_spalten.yaml (Default
    "ohne Teamangabe"); verliehene Spieler: "verliehen"."""
    if (getattr(ctx, "stand", None) or {}).get("quelle") != "live":
        return None
    if r.get("eigen") == "leihe_aus":
        return "verliehen"
    team = r.get("team")
    if team is None or pd.isna(team) or team in ("", "unbekannt"):
        return getattr(ctx, "team_ohne_liste", None) or OHNE_TEAM
    return "Profis" if team == "Senior Team" else str(team)


def _eigene(ctx) -> pd.DataFrame:
    df = ctx.df
    if "own" not in df:
        return df.iloc[0:0]
    return df[df["own"].fillna(False).astype(bool)].drop_duplicates("uid")


def _noten(conn, save: str, uid: str | None = None) -> pd.DataFrame:
    e = spiele.einsaetze(conn, save, uid)
    if e.empty:
        return e
    e = e[(e["eingesetzt"] == 1) & e["note"].notna()].copy()
    e["player_uid"] = e["player_uid"].astype(str)
    return e.sort_values(["player_uid", "datum"])


def standard_von(conn, save: str) -> str | None:
    """Default-Anfang: letzter Kader-Export der Vorsaison (Saisonbasis), sonst der erste Kader-Export."""
    snaps = per90.saison_snapshots(conn, save, ("kader",))
    if not snaps:
        return None
    vs = snaps.get(per90.vorsaison(max(snaps)), {}).get("kader")
    if vs:
        return vs[1]
    return conn.execute(
        "SELECT MIN(ingame_date) FROM snapshots WHERE save = ? AND view_type = 'kader'", (save,)
    ).fetchone()[0]


def _grenze() -> str:
    return per90.saison_cfg().get("grenze", "07-01")


# --------------------------------------------------------------------------- Übersicht und Detail


def uebersicht(ctx, conn, von: str | None = None, bis: str | None = None) -> dict:
    """Je eigener Spieler: Δ Attribute (alle, Key-Attribute des Slots), größte Veränderungen, Minuten, Ø Note."""
    if not hasattr(ctx, "team_ohne_liste"):
        ctx.team_ohne_liste = common.load_yaml("live_spalten.yaml").get("team_ohne_liste")
    eigene = _eigene(ctx)
    alle = attribut_verlauf(conn, ctx.save)
    tage = stichtage(alle)
    von = von or standard_von(conn, ctx.save)
    bis = bis or (tage[-1]["datum"] if tage else None)
    grenze = _grenze()
    ks = kader_stats(conn, ctx.save, grenze)
    noten = _noten(conn, ctx.save)
    zeilen = []
    for _, r in eigene.iterrows():
        uid = str(r["uid"])
        v = alle[alle["uid"] == uid]
        slot = slot_von(r["name"], ctx.slots_taktik)
        z = {
            "uid": uid, "name": r["name"], "alter": _w(r.get("age")), "position": _w(r.get("position")),
            "eigen": _w(r.get("eigen")), "team": team_von(ctx, r), "slot": slot, "start": None, "ende": None, "delta": None,
            "delta_key": None, "n_key": 0, "plus": [], "minus": [], "minuten": None, "note": None, "spiele": 0,
        }  # fmt: skip
        se = start_ende(_breit(v), von, bis) if not v.empty else None
        if se:
            a, e = se
            attrs = _relevant(a.index, _ist_tw(r.get("position")))
            d = (e[attrs] - a[attrs]).dropna()
            key = [k for k in key_attribute(ctx, slot) if k in d.index]
            plus = d[d > 0].sort_values(ascending=False).head(3)
            minus = d[d < 0].sort_values().head(3)
            z.update(
                start=a.name, ende=e.name, delta=_w(d.sum()), n_key=len(key),
                delta_key=_w(d[key].sum()) if key else None,
                plus=[{"attribut": k, "delta": _w(x)} for k, x in plus.items()],
                minus=[{"attribut": k, "delta": _w(x)} for k, x in minus.items()],
            )  # fmt: skip
        anf, end = z["start"] or von, z["ende"] or bis
        k = ks[ks["uid"] == uid]
        if not k.empty:
            z["minuten"] = _w(minuten_zwischen(k, anf, end, grenze))
        if not noten.empty:
            n = noten[noten["player_uid"] == uid]
            if anf:
                n = n[n["datum"] > anf]
            if end:
                n = n[n["datum"] <= end]
            z["spiele"] = len(n)
            z["note"] = _w(n["note"].mean()) if len(n) else None
        zeilen.append(z)
    zeilen.sort(key=lambda z: (z["delta"] is None, -(z["delta"] or 0), z["name"]))
    ohne = getattr(ctx, "team_ohne_liste", None) or OHNE_TEAM
    reihe = ["Profis", ohne, "U23", "U21", "U19", "U18", "U17", OHNE_TEAM, "verliehen"]
    teams = sorted({z["team"] for z in zeilen if z["team"]}, key=lambda x: (reihe.index(x) if x in reihe else 5, x))
    return {"von": von, "bis": bis, "stichtage": tage, "spieler": zeilen, "teams": teams}


def _stat_liste(ks_uid: pd.DataFrame, ist_tw: bool) -> list[tuple[str, str, str]]:
    """(Gruppe, Statistik, Bezeichnung) in der Reihenfolge des Spielerprofils, nur vorhandene Statistiken."""
    out = []
    for g, eintraege in spielerprofil.STAT_GRUPPEN.items():
        if g == "Torwart" and not ist_tw:
            continue
        for st, label in eintraege:
            if st in ks_uid and ks_uid[st].notna().any():
                out.append((g, st, label))
    return out


def _attribut_teil(v: pd.DataFrame, key: list[str], ist_tw: bool, von, bis) -> dict:
    if v.empty:
        return {"zeitraum": {"start": None, "ende": None}, "stichtage": [], "attribute": [], "key_summe": []}
    breit = _breit(v)
    q = _quelle_je_tag(v)
    se = start_ende(breit, von, bis)
    a, e = se if se else (breit.iloc[0], breit.iloc[-1])
    attribute = []
    for g, liste in spielerprofil.ATTRIBUT_GRUPPEN.items():
        if g == "Torwart" and not ist_tw:
            continue
        eintraege = []
        for n in liste:
            if n not in breit:
                continue
            s, en = a.get(n), e.get(n)
            eintraege.append({
                "name": n, "key": n in key, "start": _w(s), "ende": _w(en),
                "delta": _w(en - s) if pd.notna(s) and pd.notna(en) else None,
                "verlauf": [[d, _w(x)] for d, x in breit[n].dropna().items()],
            })  # fmt: skip
        if eintraege:
            attribute.append({"gruppe": g, "attribute": eintraege})
    k = [n for n in key if n in breit]
    key_summe = (
        [[d, _w(x)] for d, x in breit[k].sum(axis=1, min_count=1).dropna().items()] if k else []
    )
    return {
        "zeitraum": {"start": a.name, "ende": e.name},
        "stichtage": [{"datum": d, "quelle": q[d]} for d in sorted(q.index)],
        "attribute": attribute, "key_summe": key_summe,
    }  # fmt: skip


def spieler(ctx, conn, uid: str, von: str | None = None, bis: str | None = None) -> dict:
    """Detail eines eigenen Spielers: Attribut-Verlauf, Key-Summe, Per-90 je Zeitraum, Saisonvergleich, Noten."""
    uid = str(uid)
    eigene = _eigene(ctx)
    hit = eigene[eigene["uid"].astype(str) == uid]
    if hit.empty:
        common.die(f"Spieler '{uid}' ist kein eigener Spieler in den geladenen Daten.")
    r = hit.iloc[0]
    ist_tw = _ist_tw(r.get("position"))
    slot = slot_von(r["name"], ctx.slots_taktik)
    key = key_attribute(ctx, slot)
    von = von or standard_von(conn, ctx.save)
    teil = _attribut_teil(attribut_verlauf(conn, ctx.save, [uid]), key, ist_tw, von, bis)

    grenze = _grenze()
    ableit = common.load_yaml("spalten.yaml").get("abgeleitet") or {}
    ks = kader_stats(conn, ctx.save, grenze)
    ks = ks[ks["uid"] == uid]
    stats = _stat_liste(ks, ist_tw)
    namen_stats = [s for _, s, _ in stats]
    per = perioden(ks, namen_stats, ableit, grenze) if not ks.empty else []
    vergleich, w_vs, w_neu = None, {}, {}
    if not ks.empty:
        aktuell = ks["saison"].max()
        vs = per90.vorsaison(aktuell)
        je = {s: g.sort_values("datum").iloc[-1] for s, g in ks.groupby("saison")}
        if vs in je:
            vergleich = {
                "vs": {"saison": vs, "datum": je[vs]["datum"], "minuten": _w(je[vs]["minutes"])},
                "neu": {"saison": aktuell, "datum": je[aktuell]["datum"], "minuten": _w(je[aktuell]["minutes"])},
            }  # fmt: skip
            w_vs = zeitraum_werte(None, je[vs], namen_stats, ableit)
            w_neu = zeitraum_werte(None, je[aktuell], namen_stats, ableit)
    statistiken = [
        {
            "gruppe": g, "stat": s, "label": lab, "art": _art(s, ableit),
            "niedrig": s in spielerprofil.NIEDRIG_BESSER,
            "perioden": [_w(p["werte"].get(s)) for p in per],
            "vs": _w(w_vs.get(s)), "neu": _w(w_neu.get(s)),
        }
        for g, s, lab in stats
    ]  # fmt: skip

    n = _noten(conn, ctx.save, uid)
    noten = []
    if not n.empty:
        n = n.assign(gleitend=n["note"].rolling(GLEITEND, min_periods=1).mean())
        noten = [
            {
                "datum": x["datum"], "note": _w(x["note"]), "gleitend": _w(x["gleitend"]),
                "minuten": _w(x["minuten"]), "rolle": _w(x.get("rolle_kurz")), "position": _w(x.get("position")),
                "tore": _w(x.get("tore")), "vorlagen": _w(x.get("vorlagen")),
            }
            for _, x in n.iterrows()
        ]  # fmt: skip
    return {
        "spieler": {
            "uid": uid, "name": r["name"], "alter": _w(r.get("age")), "position": _w(r.get("position")),
            "eigen": _w(r.get("eigen")), "slot": slot,
        },
        "key": key, **teil,
        "perioden": [{k: _w(p[k]) for k in ("saison", "von", "bis", "minuten")} for p in per],
        "statistiken": statistiken, "saisonvergleich": vergleich, "noten": noten,
        "gleitend_n": GLEITEND, "min_zeitraum": MIN_ZEITRAUM,
    }  # fmt: skip


# --------------------------------------------------------------------------- CLI


def kontext_cli(conn, save: str, config_dir=None):
    """Leichter Kontext ohne Anker-Berechnung: eigene Spieler, Taktik-Slots, Key-Attribut-Quelle."""
    return SimpleNamespace(
        df=planer.daten_db(conn, save).rename(columns={"player_uid": "uid"}), save=save,
        ra=rollen_attr.laden(config_dir), rk=common.load_yaml("rollen_kpis.yaml", config_dir),
        slots_taktik=common.load_yaml("taktik_slots.yaml", config_dir).get("slots") or {},
        attr_schwelle=None, attr_stufe=None,
    )  # fmt: skip


def _f(v, vorzeichen=False) -> str:
    if v is None:
        return "–"
    return (f"{v:+.0f}" if vorzeichen else f"{v:.0f}").replace(".", ",")


def _ausgabe_detail(d: dict) -> None:
    s = d["spieler"]
    print(f"## {s['name']} ({s['alter']}, {s['position']}; Slot {s['slot'] or '–'}; "
          f"Key-Attribute: {', '.join(d['key']) or '–'})")  # fmt: skip
    print(f"Attribute {d['zeitraum']['start']} -> {d['zeitraum']['ende']} (* = Key-Attribut)")
    for g in d["attribute"]:
        ver = [f"{x['name']}{'*' if x['key'] else ''} {_f(x['start'])}->{_f(x['ende'])}"
               for x in g["attribute"] if x["delta"]]  # fmt: skip
        print(f"  {g['gruppe']}: {', '.join(ver) or 'keine Veränderung'}")
    if d["perioden"]:
        spalten = [f"{p['von'][2:]}..{p['bis'][2:]} ({p['minuten']:.0f})" for p in d["perioden"]]
        t = pd.DataFrame([[x["label"], x["art"], *x["perioden"]] for x in d["statistiken"]],
                         columns=["Statistik", "Art", *spalten])  # fmt: skip
        print("\nJe Zeitraum (Art p90 = pro 90, quote = %, anzahl = im Zeitraum, rate = gewichtet):")
        print(t.round(2).to_string(index=False))
    sv = d["saisonvergleich"]
    if sv:
        print(f"\nSaisonvergleich {sv['vs']['saison']} ({_f(sv['vs']['minuten'])} Min.) vs. "
              f"{sv['neu']['saison']} ({_f(sv['neu']['minuten'])} Min.)")  # fmt: skip
        t = pd.DataFrame([[x["label"], x["vs"], x["neu"]] for x in d["statistiken"]],
                         columns=["Statistik", sv["vs"]["saison"], sv["neu"]["saison"]])  # fmt: skip
        print(t.round(2).to_string(index=False))
    n = d["noten"]
    if n:
        print(f"\nNoten (SpielLogger): {len(n)} Spiele, Ø {sum(x['note'] for x in n) / len(n):.2f}; "
              f"gleitend letzte {d['gleitend_n']}: {n[-1]['gleitend']:.2f}")  # fmt: skip


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common.add_common_args(ap)
    ap.add_argument("--von", help="Anfang JJJJ-MM-TT (Default: letzter Kader-Export der Vorsaison)")
    ap.add_argument("--bis", help="Ende JJJJ-MM-TT (Default: neuester Stand)")
    ap.add_argument("--zeige", help="Detail eines eigenen Spielers (Name oder Nachname)")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    try:
        ctx = kontext_cli(conn, save, a.config_dir)
        u = uebersicht(ctx, conn, a.von, a.bis)
        print(f"# Entwicklung {save}: {u['von']} -> {u['bis']} (Attribute aus Kader-Exporten und Live-Ständen; "
              "Training und Spiele nicht trennbar)\n")  # fmt: skip
        if a.zeige:
            treffer = [z for z in u["spieler"] if namen.passt(z["name"], a.zeige)]
            treffer = treffer or [z for z in u["spieler"] if a.zeige.lower() in z["name"].lower()]
            if not treffer:
                common.die(f"Kein eigener Spieler zu '{a.zeige}'.")
            _ausgabe_detail(spieler(ctx, conn, treffer[0]["uid"], a.von, a.bis))
            return
        t = pd.DataFrame([{
            "Spieler": z["name"], "Alter": z["alter"], "Slot": z["slot"] or "", "Δ": _f(z["delta"], True),
            "Δ Key": _f(z["delta_key"], True), "von": z["start"] or "", "bis": z["ende"] or "",
            "Min.": _f(z["minuten"]), "Ø Note": z["note"], "Spiele": z["spiele"],
            "Zuwachs": ", ".join(f"{p['attribut']} {p['delta']:+.0f}" for p in z["plus"]),
            "Rückgang": ", ".join(f"{p['attribut']} {p['delta']:+.0f}" for p in z["minus"]),
        } for z in u["spieler"]])  # fmt: skip
        print(t.to_string(index=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
