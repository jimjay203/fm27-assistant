"""Rollen-Score: Spieler mit den zwei Rollen eines Slots bewerten (mit Ball + ohne Ball).

Rollen und ihre Statistik-Bausteine: config/rollen_kpis.yaml (Vorschlag von Claude, ungeprüft; Begründung in
wissen/rollen-kpis.md). Slots eurer Taktik: config/taktik_slots.yaml (Kopie aus taktik.md).

Rechnung: Statistik-Score 0..100 relativ zu den Spielern derselben Positionsgruppe (Senior Team, >= 900 Min., volle
Daten, Ligen ab --pool-min-stufe; Anker = Perzentile 25/55/90 wie in benchmark.py). Baustein-Score = Mittel seiner
Statistiken, Rollen-Score = gewichtetes Mittel der Bausteine, Paar-Score = Mittel aus Rolle mit und ohne Ball.
`paar_gew` = Paar-Score x Liga-Gewicht (Stufe der Liga, Schema je Positionsgruppe). `vs_top` = Anteil der Topclub-
Spieler derselben Positionsgruppe, den der Spieler je Statistik übertrifft (50 = Topclub-Median).

Aufruf:  uv run python scripts/rollen.py --slot "OM r" [--max-alter 28] [--top 8]
         uv run python scripts/rollen.py --alle --top 5
         uv run python scripts/rollen.py --rolle-mit "Zielspieler" --rolle-ohne "Zentraler Umschaltstürmer"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b
import common
import ligen
import live

PERZENTILE = {"schlecht": 25, "ok": 55, "gut": 90}


def aufloesen(name: str, rk: dict) -> str:
    """FM27-Rollenname -> Rolle der Quelle (alias_rollen in rollen_kpis.yaml), sonst unverändert."""
    return (rk.get("alias_rollen") or {}).get(name, name)


def _anzeige(s: dict, key: str) -> str:
    """Rollenname wie in taktik_slots.yaml; mit Hinweis, wenn er auf eine andere Rolle der Quelle abgebildet wurde."""
    n, ziel = s[f"{key}_anzeige"], s[key]
    return n if n == ziel else f"{n} (gewertet wie {ziel})"


def statistik_specs(rk: dict, rollen: list[str]) -> dict[str, dict[str, dict]]:
    """{gruppe: {stat: {stat, art, niedrig}}} für alle Statistiken der Rollen (je Positionsgruppe der Rolle)."""
    specs: dict[str, dict[str, dict]] = {}
    for name in rollen:
        r = rk["rollen"][name]
        for bn in r["bausteine"]:
            for s in rk["bausteine"][bn]["stats"]:
                specs.setdefault(r["gruppe"], {})[s["stat"]] = {
                    "stat": s["stat"],
                    "art": s["art"],
                    "niedrig": s.get("richtung") == "niedrig",
                }
    return specs


def anker_je_gruppe(df, rk, specs, lg, defaults, min_stufe="Gut", perz=None, min_n=100) -> dict:
    """Anker (schlecht/ok/gut) je Positionsgruppe und Statistik aus dem Pool; Verworfenes mit Grund."""
    perz = perz or PERZENTILE
    out = {}
    for g, stats in specs.items():
        pool = b.anker_pool(df, {"positionen": rk["positionsgruppen"][g]}, defaults, lg, min_stufe)
        res = {"n_pool": len(pool), "stats": {}, "verworfen": {}}
        for st, sp in stats.items():
            v = b.stat_values(pool, sp).dropna()
            if len(v) < min_n:
                res["verworfen"][st] = f"nur {len(v)} Werte"
                continue
            q = {
                k: float(np.percentile(v, 100 - p if sp["niedrig"] else p)) for k, p in perz.items()
            }
            a, o, gu = q["schlecht"], q["ok"], q["gut"]
            if not ((a < o < gu) or (a > o > gu)):
                res["verworfen"][st] = f"Anker nicht trennscharf ({a:.2f}/{o:.2f}/{gu:.2f})"
                continue
            res["stats"][st] = {"stat": st, "art": sp["art"], "schlecht": a, "ok": o, "gut": gu}
        out[g] = res
    return out


def topclub_referenz_je_gruppe(
    df, rk, specs, clubs, defaults, min_n=15
) -> dict[str, dict[str, np.ndarray]]:
    """Sortierte Werte der Topclub-Spieler je Positionsgruppe und Statistik."""
    ref = {}
    for g, stats in specs.items():
        pool = df[
            df["club"].isin(clubs) & (df["minutes"].fillna(0) >= defaults.get("min_minuten", 900))
        ]
        pool = pool[(pool["team"] == "Senior Team") & (pool["datenbasis"] == "voll")]
        pool = pool[
            pool["position"].map(lambda p, g=g: b.position_ok(p, rk["positionsgruppen"][g]))
        ]
        ref[g] = {}
        for st, sp in stats.items():
            v = np.sort(b.stat_values(pool, sp).dropna().to_numpy())
            if len(v) >= min_n:
                ref[g][st] = v
    return ref


def _gewichtet(
    parts: dict[str, pd.Series], weights: dict[str, float], min_abdeckung: float, index
) -> pd.Series:
    """Gewichtetes Mittel über vorhandene Bausteine; NaN, wenn weniger als min_abdeckung des Gewichts vorliegt."""
    if not parts:
        return pd.Series(np.nan, index=index)
    num = sum(weights[k] * parts[k].fillna(0) for k in parts)
    have = sum(weights[k] * parts[k].notna() for k in parts)
    total = sum(weights.values())
    return (num / have.where(have > 0)).where(have >= min_abdeckung * total - 1e-9)


def rolle_bewerten(
    sub: pd.DataFrame, name: str, rk: dict, anker_g: dict, ref_g: dict, min_abdeckung=0.6
):
    """-> (score, vs_top, Baustein-Scores). Statistiken ohne Anker entfallen; Bausteine ohne Statistik auch."""
    r = rk["rollen"][name]
    weights = {bn: float(w) for bn, w in r["bausteine"].items()}
    parts, tops = {}, {}
    for bn in weights:
        sc, tp = [], []
        for s in rk["bausteine"][bn]["stats"]:
            a = anker_g["stats"].get(s["stat"])
            if not a:
                continue
            v = b.stat_values(sub, a)
            sc.append(b.stat_scores(v, a))
            rf = ref_g.get(s["stat"])
            if rf is not None:
                tp.append(
                    pd.Series(
                        b.prozent_im_referenz(rf, v, a["schlecht"] > a["gut"]), index=sub.index
                    )
                )
        if sc:
            parts[bn] = pd.concat(sc, axis=1).mean(axis=1)
        if tp:
            tops[bn] = pd.concat(tp, axis=1).mean(axis=1)
    detail = pd.DataFrame(parts, index=sub.index)
    return (
        _gewichtet(parts, weights, min_abdeckung, sub.index),
        _gewichtet(tops, weights, min_abdeckung, sub.index),
        detail,
    )


def paar_bewerten(sub, mit, ohne, rk, anker, ref, defaults) -> pd.DataFrame:
    """Spalten: mit, ohne, paar, vs_top (Mittel der beiden Rollen mit phasen_gewicht)."""
    gm, go = rk["rollen"][mit]["gruppe"], rk["rollen"][ohne]["gruppe"]
    s_m, t_m, d_m = rolle_bewerten(sub, mit, rk, anker[gm], ref[gm])
    s_o, t_o, d_o = rolle_bewerten(sub, ohne, rk, anker[go], ref[go])
    pg = rk.get("phasen_gewicht", {"mit": 0.5, "ohne": 0.5})
    paar = (pg["mit"] * s_m + pg["ohne"] * s_o).where(s_m.notna() & s_o.notna())
    top = (pg["mit"] * t_m + pg["ohne"] * t_o).where(t_m.notna() & t_o.notna())
    out = pd.DataFrame({"mit": s_m, "ohne": s_o, "paar": paar, "vs_top": top}, index=sub.index)
    out.attrs["detail"] = (d_m, d_o)
    return out


def kandidaten_slot(df, mit, ohne, rk, anker, ref, defaults, lg, a, eigene_min):
    """-> (eigene, kandidaten) als bewertete Tabellen für das Rollenpaar."""
    rules = rk["positionsgruppen"][rk["rollen"][mit]["gruppe"]]
    base = df[df["team"] == "Senior Team"]
    base = base[base["position"].map(lambda p: b.position_ok(p, rules))]
    own = base[base["own"] & (base["minutes"].fillna(0) >= eigene_min)]
    cand = base[~base["own"] & (base["minutes"].fillna(0) >= a.min_minuten)]
    if a.nur_volle_daten:
        cand = cand[cand["datenbasis"] == "voll"]
    if a.max_alter is not None:
        cand = cand[cand["age"] <= a.max_alter]
    if a.max_wert_mio is not None:
        cand = cand[cand["value"] <= a.max_wert_mio * 1e6]  # ohne Marktwert (NaN) fällt heraus
    res = []
    for sub in (own, cand):
        sub = sub.copy()
        sc = paar_bewerten(sub, mit, ohne, rk, anker, ref, defaults)
        sub = pd.concat([sub, sc], axis=1)
        sub["liga_stufe"] = sub["league"].map(lg.stufe)
        schema = a.gewichtung or rk["gewichtung_je_gruppe"][rk["rollen"][mit]["gruppe"]]
        if schema != "aus":
            sub["liga_gewicht"] = sub["league"].map(lambda d, s=schema: lg.gewicht(d, s))
            sub["paar_gew"] = sub["paar"] * sub["liga_gewicht"]
        else:
            sub["paar_gew"] = sub["paar"]
        res.append(sub[sub["paar"].notna()])
    own_r, cand_r = res
    if a.min_stufe:
        lim = lg.stufe_index(a.min_stufe)
        ok = cand_r["liga_stufe"].map(lambda x: isinstance(x, str) and lg.stufe_index(x) <= lim)
        cand_r = cand_r[ok.astype(bool)]  # bool: eine leere object-Series würde Spalten wählen
    cand_r = cand_r[cand_r["paar_gew"].notna()]
    return own_r, cand_r


COLS = [
    "name",
    "club",
    "liga_stufe",
    "age",
    "minutes",
    "mit",
    "ohne",
    "paar",
    "paar_gew",
    "vs_top",
    "wert_mio",
    "contract_end",
]


def _tabelle(t: pd.DataFrame) -> str:
    from tabulate import tabulate

    t = t.assign(wert_mio=t["value"] / 1e6)
    if "eigen" in t and t["own"].any():
        t = t.assign(status=t["eigen"].fillna(""))
        cols = [*COLS[:2], "status", *COLS[2:]]
    else:
        cols = COLS
    return tabulate(t[cols].round(1), headers="keys", tablefmt="github", showindex=False)


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--slot", help="Slot aus config/taktik_slots.yaml, z. B. 'OM r'")
    ap.add_argument("--alle", action="store_true", help="alle Slots der Taktik")
    ap.add_argument("--rolle-mit", help="Rolle mit Ball (statt --slot)")
    ap.add_argument("--rolle-ohne", help="Rolle ohne Ball (statt --slot)")
    ap.add_argument("--url", default=live.DEFAULT_URL)
    ap.add_argument("--min-minuten", type=int, default=900, help="Kandidaten (Default 900)")
    ap.add_argument(
        "--min-minuten-eigene", type=int, default=400, help="eigene Spieler (Default 400)"
    )
    ap.add_argument("--max-alter", type=int)
    ap.add_argument(
        "--max-wert-mio", type=float, help="Kandidaten nur bis zu diesem Basiswert (Mio.)"
    )
    ap.add_argument("--min-stufe", help="Kandidaten nur aus Ligen ab dieser Stufe, z. B. 'Gut'")
    ap.add_argument(
        "--pool-min-stufe", default="Gut", help="Vergleichspool der Anker (Default: Gut)"
    )
    ap.add_argument(
        "--gewichtung", help="Schema aus ligen.yaml oder 'aus' (Default: je Positionsgruppe)"
    )
    ap.add_argument("--nur-volle-daten", action="store_true")
    ap.add_argument("--topclubs", type=int, default=20)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--detail", metavar="NAME", help="Baustein-Scores für Spieler mit diesem Namen")
    a = ap.parse_args(argv)

    rk = common.load_yaml("rollen_kpis.yaml", a.config_dir)
    slots = (common.load_yaml("taktik_slots.yaml", a.config_dir).get("slots")) or {}
    if a.alle:
        todo = dict(slots)
    elif a.slot:
        if a.slot not in slots:
            common.die(f"Slot '{a.slot}' fehlt. Vorhanden: {', '.join(slots)}")
        todo = {a.slot: slots[a.slot]}
    elif a.rolle_mit and a.rolle_ohne:
        todo = {f"{a.rolle_mit} / {a.rolle_ohne}": {"mit": a.rolle_mit, "ohne": a.rolle_ohne}}
    else:
        common.die("Bitte --slot, --alle oder --rolle-mit und --rolle-ohne angeben.")
    for s in todo.values():
        for key in ("mit", "ohne"):
            s[f"{key}_anzeige"] = s[key]  # Name wie in taktik_slots.yaml (FM27-Name)
            s[key] = aufloesen(s[key], rk)
            if s[key] not in rk["rollen"]:
                common.die(
                    f"Rolle '{s[f'{key}_anzeige']}' fehlt in config/rollen_kpis.yaml (auch nicht als alias_rollen)."
                )

    cfg = common.load_yaml("profile.yaml", a.config_dir)
    defaults = cfg.get("defaults", {})
    lg = ligen.Ligen.laden(a.config_dir)
    df = b.load_live(
        a.url,
        common.load_yaml("live_spalten.yaml", a.config_dir),
        common.load_yaml("spalten.yaml", a.config_dir).get("abgeleitet") or {},
    )
    if df.empty:
        common.die("Keine Spielerdaten (Save geladen? Reader läuft?).")
    rollen = sorted({r for s in todo.values() for r in (s["mit"], s["ohne"])})
    specs = statistik_specs(rk, rollen)
    anker = anker_je_gruppe(df, rk, specs, lg, defaults, a.pool_min_stufe)
    clubs = b.topclub_liste(df, a.topclubs)
    ref = topclub_referenz_je_gruppe(df, rk, specs, clubs, defaults)

    print(
        f"# Rollen-Score (Daten vom {df.attrs.get('date')}; Anker: Perzentile {list(PERZENTILE.values())} der Spieler "
        f"gleicher Positionsgruppe in Ligen ab '{a.pool_min_stufe}'; Rollen-Zuordnung ungeprüft, siehe wissen/rollen-kpis.md)"
    )
    for name, s in todo.items():
        own, cand = kandidaten_slot(
            df, s["mit"], s["ohne"], rk, anker, ref, defaults, lg, a, a.min_minuten_eigene
        )
        rm, ro = rk["rollen"][s["mit"]], rk["rollen"][s["ohne"]]

        print(
            f"\n## {name}: {_anzeige(s, 'mit')} (Zuverlässigkeit {rm['verlaesslichkeit']}) / {_anzeige(s, 'ohne')} (Zuverlässigkeit {ro['verlaesslichkeit']})"
        )
        for r in (rm, ro):
            if r.get("luecken") and r["verlaesslichkeit"] == "gering":
                print(f"  Hinweis: {r['luecken']}")
        if s.get("hinweis"):
            print(f"  Hinweis Zuordnung: {s['hinweis']}")
        if s.get("stamm"):
            print(f"  Laut taktik.md eingesetzt: {', '.join(s['stamm'])}")
        if a.detail:
            for sub in (own, cand):
                hit = sub[sub["name"].fillna("").str.contains(a.detail, case=False)]
                for idx, r in hit.iterrows():
                    d_m, d_o = paar_bewerten(
                        sub.loc[[idx]], s["mit"], s["ohne"], rk, anker, ref, defaults
                    ).attrs["detail"]
                    print(
                        f"\n  {r['name']} ({r['club']}): mit {r['mit']:.0f} / ohne {r['ohne']:.0f}"
                    )
                    for lbl, d in ((s["mit"], d_m), (s["ohne"], d_o)):
                        print(
                            f"    {lbl}: "
                            + ", ".join(f"{bn} {v:.0f}" for bn, v in d.iloc[0].dropna().items())
                        )
            continue
        print(f"\nEigene Spieler (ab {a.min_minuten_eigene} Min.), n={len(own)}")
        print(_tabelle(own.sort_values("paar", ascending=False)) if len(own) else "  keine")
        top = cand.sort_values("paar_gew", ascending=False).head(a.top)
        print(f"\nKandidaten (Top {a.top} von {len(cand)}, sortiert nach paar_gew)")
        print(_tabelle(top) if len(top) else "  keine")
    print(
        "\npaar = Mittel aus mit und ohne Ball (0 = Schlecht, 50 = OK, 100 = Gut; Perzentile 25/55/90 des Pools). "
        f"vs_top: 50 = Topclub-Median. Topclubs = Top {a.topclubs} nach Kaderwert. Marktwert = gespeicherter Basiswert."
    )


if __name__ == "__main__":
    main()
