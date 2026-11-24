"""Benchmark-Score: Spieler gegen absolute Maßstäbe (Schlecht/OK/Gut) je Rollentyp (config/profile.yaml).

Quelle der Maßstäbe: FM Stag "What does Good look like in FM24?" (aus FM24, für FM27 ungeprüft), siehe
wissen/benchmarks-fm24.md. `--kalibrierung` zeigt, wo diese Maßstäbe in euren FM27-Daten liegen.

Score je Statistik: Schlecht = 0, OK = 50, Gut = 100 (linear, geklemmt). Profil-Score = Mittel der
vorhandenen Statistiken, wenn mindestens `min_abdeckung` der Statistiken vorliegt.

Datenquelle: `--quelle live` (Default, FMMT-27-Server, schreibt nichts) oder `--quelle db` (Snapshots).
Eigene Spieler sind nur in der Live-Quelle markiert.

Aufruf:  uv run python scripts/benchmark.py --profil stuermer_torjaeger [--max-alter 28] [--top 25]
         uv run python scripts/benchmark.py --profil stuermer_torjaeger --detail "Füllkrug"
         uv run python scripts/benchmark.py --profil stuermer_torjaeger --kalibrierung
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fmparse
import ligen
import live
import per90

SIDE_ALIAS = {"Z": "C"}  # deutsche Exporte: Z = zentral
FULL_DIST_KM = (
    8.5  # wie im Reader: darunter fehlen Laufdaten, die Liga hat nur den reduzierten Satz
)


def parse_positions(pos) -> list[tuple[str, set[str]]]:
    """'D (RC), DM, M/OM (Z)' / 'V/FV (R)' -> [('D', {R,C}), ('DM', set()), ...] mit normalisierten Kürzeln."""
    out = []
    for part in str(pos or "").split(","):
        m = re.match(r"\s*([A-Za-zÄÖÜ/]+)\s*(?:\(([A-Z]+)\))?", part)
        if not m:
            continue
        sides = {SIDE_ALIAS.get(ch, ch) for ch in (m.group(2) or "")}
        for tok in m.group(1).split("/"):
            tok = tok.upper()
            out.append((per90.POS_ALIAS.get(tok, tok), sides))
    return out


def position_ok(pos, rules: list[dict]) -> bool:
    """True, wenn eine Position des Spielers zu einer Regel passt (pos + optional Seiten)."""
    for p, sides in parse_positions(pos):
        for r in rules:
            if p == r["pos"] and (not r.get("seiten") or sides & set(r["seiten"])):
                return True
    return False


def stat_values(df: pd.DataFrame, spec: dict) -> pd.Series:
    col = spec["stat"]
    if col not in df:
        return pd.Series(np.nan, index=df.index)
    v = df[col].astype(float)
    if spec["art"] == "p90":
        v = v / df["minutes"].astype(float).where(df["minutes"] > 0) * 90
    return v


def stat_scores(v: pd.Series, spec: dict) -> pd.Series:
    """Schlecht=0, OK=50, Gut=100; niedriger ist besser, wenn schlecht > gut. NaN bleibt NaN."""
    lo, mid, hi = spec["schlecht"], spec["ok"], spec["gut"]
    if hi >= lo:
        s = np.interp(v, [lo, mid, hi], [0, 50, 100])
    else:
        s = np.interp(v, [hi, mid, lo], [100, 50, 0])
    return pd.Series(np.where(v.isna(), np.nan, s), index=v.index)


def score_profile(
    df: pd.DataFrame, profile: dict, defaults: dict, min_minuten: int | None = None
) -> pd.DataFrame:
    """Spieler des Profils (Position, Minuten) mit score, n_stats, spitze und Einzelwerten (v_/s_<stat>)."""
    threshold = min_minuten if min_minuten is not None else defaults.get("min_minuten", 900)
    sub = df[df["minutes"].fillna(0) >= threshold]
    sub = sub[sub["position"].map(lambda p: position_ok(p, profile["positionen"]))].copy()
    specs = profile["stats"]
    scores = {}
    for sp in specs:
        v = stat_values(sub, sp)
        sub[f"v_{sp['stat']}"] = v
        scores[sp["stat"]] = stat_scores(v, sp)
        sub[f"s_{sp['stat']}"] = scores[sp["stat"]]
    s = pd.DataFrame(scores)
    sub["n_stats"] = s.notna().sum(axis=1)
    sub["score"] = s.mean(axis=1).where(
        sub["n_stats"] >= defaults.get("min_abdeckung", 0.6) * len(specs)
    )
    sub["spitze"] = (s >= 100).sum(axis=1)
    return sub


def _fehlt(x) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x))


def datenbasis(position, minutes, stats: dict) -> str:
    """'voll' oder 'reduziert': Liga mit vollem Statistiksatz (Laufdaten) oder nur dem reduzierten."""
    if any(t == "GK" for t, _ in parse_positions(position)):
        # Torhüter laufen kaum: Datensatz an den Torwart-Stats erkennen
        return "reduziert" if _fehlt(stats.get("par_pct")) else "voll"
    dist = stats.get("distanz_km")
    voll = (
        not _fehlt(dist)
        and not _fehlt(minutes)
        and minutes
        and dist / minutes * 90 >= FULL_DIST_KM
        and not _fehlt(stats.get("sprints_p90"))
    )
    return "voll" if voll else "reduziert"


def datenbasis_spalte(df: pd.DataFrame) -> pd.Series:
    """`datenbasis` je Zeile eines DataFrames (Exporte: dieselbe Regel wie live)."""
    stats = [c for c in ("par_pct", "distanz_km", "sprints_p90") if c in df]
    return pd.Series(
        [datenbasis(p, m, dict(zip(stats, v, strict=True))) for p, m, *v in
         zip(df["position"], df["minutes"], *(df[c] for c in stats), strict=True)],
        index=df.index, dtype=object,
    )  # fmt: skip


def load_live(url: str, cfg: dict, derived: dict) -> pd.DataFrame:
    resp = live.api_get(url, "/api/players?scope=competitive&all=1")
    own = live.own_club_uids(resp)
    recs = []
    for r in resp.get("rows") or []:
        c = live.convert_row(r, cfg, own, derived)
        k, st = c["core"], c["stats"]
        recs.append(
            {"uid": c["uid"], "own": c["own"], "eigen": c["info"].get("eigen"), "team": c["info"]["team"],
             "datenbasis": datenbasis(k["position"], k["minutes"], st), **k, **st}
        )  # fmt: skip
    df = pd.DataFrame(recs)
    df.attrs["date"] = resp.get("date")
    return df


def load_db(conn, save: str, eigene: bool = False, config_dir=None) -> pd.DataFrame:
    """Spieler mit Saisonbasis (per90.load_saison): je Quelle (Kader, Suche, Live) der letzte Snapshot der laufenden
    Saison und der Vorsaison, Vorsaison gewichtet (config/saison.yaml). Ältere Suchen derselben Saison sind veraltet.

    `eigene`: Spieler des neuesten Kader-Snapshots als eigene markieren (own, eigen = kader, team = Senior Team);
    sonst own = False wie bisher (eigene Spieler markiert sonst nur die Live-Quelle)."""
    players, _ = per90.load_saison(conn, save, config_dir=config_dir)
    s = players.attrs.get("saison") or {}
    snaps = {**(s.get("vs") or {}), **(s.get("neu") or {})}  # je Quelle der neueste
    players = players.rename(columns={"player_uid": "uid"})
    players.attrs["date"] = max((d for _, d in snaps.values() if d), default=None)
    players.attrs["snapshots"] = {v: d for v, (_, d) in snaps.items()}
    players.attrs["saison"] = s
    if not len(players):
        return players
    players["league"] = ligen.mit_land(players)  # gleichnamige Ligen (Bundesliga DE/AT) eindeutig
    kader = snaps.get("kader")
    players["own"] = (players["snapshot_id"] == kader[0]) if eigene and kader else False
    if eigene:
        players["eigen"] = np.where(players["own"], "kader", None)
        if "team" not in players:
            players["team"] = "Senior Team"  # Exporte haben kein Team-Feld
    players["datenbasis"] = datenbasis_spalte(players)
    return players


def load_live_saison(
    url: str, cfg: dict, derived: dict, conn, save: str, config_dir=None
) -> pd.DataFrame:
    """load_live() mit Saisonbasis: Vorsaison aus der DB dazu (per90.mit_vorsaison), datenbasis neu berechnet."""
    df = load_live(url, cfg, derived)
    if df.empty:
        return df
    datum = fmparse.parse_date(df.attrs.get("date"))
    df = per90.mit_vorsaison(conn, save, df, datum, config_dir=config_dir)
    df["datenbasis"] = datenbasis_spalte(df)
    return df


def calibration(df: pd.DataFrame, profile: dict, defaults: dict) -> pd.DataFrame:
    """Wo liegen Schlecht/OK/Gut in euren Daten? Perzentil der Anker im Pool (Profil-Position, ab Mindestminuten)."""
    pool = df[df["minutes"].fillna(0) >= defaults.get("min_minuten", 900)]
    pool = pool[pool["position"].map(lambda p: position_ok(p, profile["positionen"]))]
    if "datenbasis" in pool and (pool["datenbasis"] == "voll").any():
        pool = pool[
            pool["datenbasis"] == "voll"
        ]  # volle Ligen: die reduzierten verzerren die Verteilung
    rows = []
    for sp in profile["stats"]:
        v = stat_values(pool, sp).dropna()
        if v.empty:
            rows.append({"statistik": sp["label"], "n": 0})
            continue

        def pct(x, v=v):
            return float((v < x).mean() * 100 + (v == x).mean() * 50)

        better_low = sp["schlecht"] > sp["gut"]
        row = {"statistik": sp["label"], "n": len(v), "median": float(v.median())}
        for k in ("schlecht", "ok", "gut"):
            p = pct(sp[k])
            row[f"{k}_perzentil"] = 100 - p if better_low else p  # immer: hoch = gut
        rows.append(row)
    return pd.DataFrame(rows)


def topclub_liste(df: pd.DataFrame, n: int = 20) -> list[str]:
    """Die n Vereine mit der größten Summe der Marktwerte im Senior Team (aus den Daten, keine Handliste)."""
    sen = df[df["team"] == "Senior Team"] if "team" in df else df
    return sen.groupby("club")["value"].sum().nlargest(n).index.tolist()


def topclub_referenz(
    df: pd.DataFrame, prof: dict, defaults: dict, clubs: list[str], min_n: int = 15
) -> dict[str, np.ndarray]:
    """Je Statistik die sortierten Werte der Topclub-Spieler dieser Rolle (Senior, ab Mindestminuten, volle Daten)."""
    pool = df[
        statistik_liga(df, "club").isin(clubs)
        & (df["minutes"].fillna(0) >= defaults.get("min_minuten", 900))
    ]
    if "team" in pool:
        pool = pool[pool["team"] == "Senior Team"]
    if "datenbasis" in pool:
        pool = pool[pool["datenbasis"] == "voll"]
    pool = pool[pool["position"].map(lambda p: position_ok(p, prof["positionen"]))]
    ref = {}
    for sp in prof["stats"]:
        v = np.sort(stat_values(pool, sp).dropna().to_numpy())
        if len(v) >= min_n:
            ref[sp["stat"]] = v
    return ref


def prozent_im_referenz(ref: np.ndarray, v, niedriger_besser: bool = False) -> np.ndarray:
    """Anteil der Referenzwerte (in %), den `v` übertrifft; Gleichstände zählen halb. NaN bleibt NaN."""
    v = np.asarray(v, dtype=float)
    p = (
        (np.searchsorted(ref, v, side="left") + np.searchsorted(ref, v, side="right"))
        / 2
        / len(ref)
        * 100
    )
    p = 100 - p if niedriger_besser else p
    return np.where(np.isnan(v), np.nan, p)


def vs_topclub(sc: pd.DataFrame, prof: dict, ref: dict[str, np.ndarray]) -> pd.Series:
    """Mittel über die Statistiken des Anteils der Topclub-Spieler dieser Rolle, den der Spieler übertrifft.

    50 = so gut wie der Median der Topclub-Spieler, 100 = besser als alle. NaN, wenn keine Referenz vorliegt."""
    cols = {
        sp["stat"]: prozent_im_referenz(
            ref[sp["stat"]], sc[f"v_{sp['stat']}"], sp["schlecht"] > sp["gut"]
        )
        for sp in prof["stats"]
        if sp["stat"] in ref
    }
    if not cols:
        return pd.Series(np.nan, index=sc.index)
    return pd.DataFrame(cols, index=sc.index).mean(axis=1)


ANKER_DATEI = "anker_fm27.yaml"
# Setzung. Jimmy hat die Umrechnung auf FM27-Daten am 2026-11-22 beauftragt.
STANDARD_PERZENTILE = {"schlecht": 25, "ok": 55, "gut": 90}


def statistik_liga(df: pd.DataFrame, spalte: str = "league") -> pd.Series:
    """Liga (bzw. Verein mit spalte="club"), in der die Statistiken überwiegend entstanden sind (Saisonbasis): die
    der Vorsaison, solange deren gewichtete Minuten überwiegen, sonst die aktuelle. Ohne Saisonspalten: aktuell."""
    if f"{spalte}_vs" not in df or "min_vs_w" not in df:
        return df[spalte]
    vs = df[f"{spalte}_vs"].notna() & (df["min_vs_w"].fillna(0) > df["min_neu"].fillna(0))
    return df[f"{spalte}_vs"].where(vs, df[spalte])


def anker_pool(
    df: pd.DataFrame, prof: dict, defaults: dict, lg: ligen.Ligen, min_stufe: str
) -> pd.DataFrame:
    """Vergleichspool eines Profils: Senior Team, ab Mindestminuten, volle Daten, Position, Liga ab `min_stufe`."""
    pool = df[df["minutes"].fillna(0) >= defaults.get("min_minuten", 900)]
    if "team" in pool:
        pool = pool[pool["team"] == "Senior Team"]
    if "datenbasis" in pool:
        pool = pool[pool["datenbasis"] == "voll"]
    pool = pool[pool["position"].map(lambda p: position_ok(p, prof["positionen"]))]
    limit = lg.stufe_index(min_stufe)
    ok = (
        statistik_liga(pool)
        .map(lg.stufe)
        .map(lambda x: isinstance(x, str) and lg.stufe_index(x) <= limit)
    )
    return pool[ok]


def berechne_anker(
    df: pd.DataFrame,
    cfg: dict,
    lg: ligen.Ligen,
    min_stufe: str = "Gut",
    perz: dict | None = None,
    min_n: int = 100,
) -> dict:
    """FM27-Anker je Profil und Statistik aus der Verteilung im Pool.

    Schlecht/OK/Gut = Perzentile `perz` der Werte (bei 'niedriger ist besser' gespiegelt). Statistiken ohne
    genug Werte oder ohne trennscharfe Anker (z. B. Median 0) werden verworfen und mit Grund gemeldet."""
    perz = perz or STANDARD_PERZENTILE
    out = {}
    for pid, prof in cfg["profile"].items():
        pool = anker_pool(df, prof, cfg.get("defaults", {}), lg, min_stufe)
        stats, verworfen = {}, {}
        for sp in prof["stats"]:
            v = stat_values(pool, sp).dropna()
            if len(v) < min_n:
                verworfen[sp["stat"]] = f"nur {len(v)} Werte (< {min_n})"
                continue
            low_better = sp["schlecht"] > sp["gut"]
            q = {k: float(np.percentile(v, 100 - p if low_better else p)) for k, p in perz.items()}
            a, o, g = q["schlecht"], q["ok"], q["gut"]
            if not ((a < o < g) or (a > o > g)):
                verworfen[sp["stat"]] = f"Anker nicht trennscharf ({a:.2f} / {o:.2f} / {g:.2f})"
                continue
            stats[sp["stat"]] = {
                "schlecht": round(a, 4),
                "ok": round(o, 4),
                "gut": round(g, 4),
                "n": len(v),
            }
        out[pid] = {"n_pool": len(pool), "stats": stats, "verworfen": verworfen}
    return out


def anker_anwenden(prof: dict, anker_prof: dict | None) -> dict:
    """Kopie des Profils mit FM27-Ankern; Statistiken ohne FM27-Anker entfallen."""
    p = copy.deepcopy(prof)
    kept = []
    for sp in p["stats"]:
        a = ((anker_prof or {}).get("stats") or {}).get(sp["stat"])
        if a:
            sp.update(schlecht=a["schlecht"], ok=a["ok"], gut=a["gut"])
            kept.append(sp)
    p["stats"] = kept
    return p


def _anker_schreiben(a, df: pd.DataFrame, cfg: dict) -> None:
    import yaml
    from tabulate import tabulate

    lg = ligen.Ligen.laden(a.config_dir)
    try:
        perz = dict(
            zip(("schlecht", "ok", "gut"), (float(x) for x in a.perzentile.split(",")), strict=True)
        )
        lg.stufe_index(a.pool_min_stufe)
    except ValueError:
        common.die(
            "--perzentile braucht drei Zahlen 'schlecht,ok,gut', --pool-min-stufe eine bekannte Stufe."
        )
    res = berechne_anker(df, cfg, lg, a.pool_min_stufe, perz)
    mins = cfg.get("defaults", {}).get("min_minuten", 900)
    meta = {
        "erstellt_aus": f"FMMT-27 live, Spielstand {df.attrs.get('date')}",
        "pool": f"Senior Team, ab {mins} Min., volle Daten, Position des Profils, Ligen ab Stufe {a.pool_min_stufe}",
        "perzentile": {k: int(v) if v == int(v) else v for k, v in perz.items()},
        "hinweis": "Erzeugt von scripts/benchmark.py --anker-berechnen. Schlecht/OK/Gut = diese Perzentile der "
        "Pool-Werte (bei 'niedriger ist besser' gespiegelt). Setzung, kein Messwert.",
    }
    path = (a.config_dir or common.ROOT / "config") / ANKER_DATEI
    head = "# Automatisch erzeugt, nicht von Hand ändern (neu erzeugen: benchmark.py --anker-berechnen).\n"
    path.write_text(
        head + yaml.safe_dump({"meta": meta, "profile": res}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    rows, dropped = [], []
    for pid, prof in cfg["profile"].items():
        for sp in prof["stats"]:
            n = res[pid]["stats"].get(sp["stat"])
            if n:
                rows.append(
                    (
                        prof["name"][:26],
                        sp["label"][:30],
                        f"{sp['schlecht']} / {sp['ok']} / {sp['gut']}",
                        f"{n['schlecht']:.2f} / {n['ok']:.2f} / {n['gut']:.2f}",
                        n["n"],
                    )
                )
        dropped += [(prof["name"], st, g) for st, g in res[pid]["verworfen"].items()]
    print(f"Anker FM27 -> {path}\nPool: {meta['pool']}; Perzentile {meta['perzentile']}")
    heads = ["Profil", "Statistik", "FM24 (S / O / G)", "FM27 (S / O / G)", "n"]
    print(tabulate(rows, headers=heads, tablefmt="github"))
    if dropped:
        print("\nVerworfen (kein FM27-Anker, Statistik entfällt):")
        for p, st, g in dropped:
            print(f"  {p}: {st} - {g}")


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--profil", help="Profil aus config/profile.yaml (Pflicht, außer bei --anker-berechnen)"
    )
    ap.add_argument(
        "--anker",
        choices=["fm27", "fm24"],
        default="fm27",
        help="Maßstäbe: fm27 = aus euren Daten (config/anker_fm27.yaml), fm24 = Original der Quelle",
    )
    ap.add_argument(
        "--anker-berechnen",
        action="store_true",
        help="FM27-Anker aller Profile aus dem Live-Pool berechnen und config/anker_fm27.yaml schreiben",
    )
    ap.add_argument("--pool-min-stufe", default="Gut", help="Pool der Anker: Ligen ab dieser Stufe")
    ap.add_argument(
        "--perzentile", default="25,55,90", help="Perzentile für Schlecht,OK,Gut (Setzung)"
    )
    ap.add_argument("--quelle", choices=["live", "db"], default="live")
    ap.add_argument("--url", default=live.DEFAULT_URL)
    ap.add_argument("--min-minuten", type=int)
    ap.add_argument("--max-alter", type=int)
    ap.add_argument("--liga", help="Teil des Liganamens, z. B. 'Bundesliga'")
    ap.add_argument("--nur-volle-daten", action="store_true", help="nur Ligen mit vollem Datensatz")
    ap.add_argument(
        "--gewichtung",
        default=None,
        help="Liga-Gewichtung nach Ansehen-Stufe: aus | standard | mild | steil | eigenes Schema aus "
        "ligen.yaml (Default: gewichtung_standard). Ligen ohne Alias fallen dabei heraus.",
    )
    ap.add_argument(
        "--min-stufe",
        help="nur Ligen ab dieser Ansehen-Stufe, z. B. 'Gut' (Herausragend > Exzellent > Beeindruckend > Gut > "
        "Recht gut > Brauchbar > Durchschnittlich)",
    )
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument(
        "--topclubs",
        type=int,
        help="Anzahl Topclubs für vs_topclub (Default: defaults.topclubs, 20; nach Summe der Marktwerte)",
    )
    ap.add_argument(
        "--detail",
        metavar="NAME",
        help="Einzelwerte aller Statistiken für Spieler mit diesem Namen",
    )
    ap.add_argument(
        "--kalibrierung", action="store_true", help="Perzentile der Maßstäbe in euren Daten"
    )
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args(argv)

    cfg = common.load_yaml("profile.yaml", a.config_dir)
    prof = (cfg.get("profile") or {}).get(a.profil) if a.profil else None
    if prof is None and not a.anker_berechnen:
        common.die(
            f"Profil '{a.profil}' fehlt in config/profile.yaml. Vorhanden: {', '.join(cfg.get('profile', {}))}"
        )
    defaults = cfg.get("defaults", {})
    if a.quelle == "live":
        live_cfg = common.load_yaml("live_spalten.yaml", a.config_dir)
        derived = common.load_yaml("spalten.yaml", a.config_dir).get("abgeleitet") or {}
        conn = common.connect(a.db)
        save = common.resolve_save(a.save)
        df = load_live_saison(a.url, live_cfg, derived, conn, save, a.config_dir)
    else:
        df = load_db(common.connect(a.db), common.resolve_save(a.save), config_dir=a.config_dir)
    if df.empty:
        common.die("Keine Spielerdaten.")

    if a.anker_berechnen:
        _anker_schreiben(a, df, cfg)
        return
    anker_info = "Anker aus FM24 (Quelle FM Stag), für FM27 ungeprüft"
    if a.anker == "fm27":
        anker_cfg = common.load_yaml(ANKER_DATEI, a.config_dir)
        if anker_cfg:
            prof = anker_anwenden(prof, (anker_cfg.get("profile") or {}).get(a.profil))
            m = anker_cfg.get("meta") or {}
            pz = m.get("perzentile") or {}
            anker_info = (
                f"Anker aus FM27-Daten ({m.get('erstellt_aus', '?')}; Pool: {m.get('pool', '?')}; "
                f"Score 0/50/100 = P{pz.get('schlecht')}/P{pz.get('ok')}/P{pz.get('gut')})"
            )
        else:
            print(
                "HINWEIS: config/anker_fm27.yaml fehlt, es gelten die FM24-Anker (--anker-berechnen).",
                file=sys.stderr,
            )

    if a.kalibrierung:
        from tabulate import tabulate

        cal = calibration(df, prof, defaults)
        print(
            f"Kalibrierung {prof['name']}: Perzentil der Maßstäbe im Pool (hoch = gut), Daten vom {df.attrs.get('date')}"
        )
        print(tabulate(cal.round(2), headers="keys", tablefmt="github", showindex=False))
        print(
            "\nLesart: Passt die FM24-Skala, liegen 'schlecht' bei etwa 10-25, 'ok' bei 40-60 und 'gut' bei 75-95."
        )
        return

    sc = score_profile(df, prof, defaults, a.min_minuten)
    if defaults.get("nur_senior", True) and "team" in sc:
        sc = sc[sc["team"] == "Senior Team"]
    if a.nur_volle_daten:
        sc = sc[sc["datenbasis"] == "voll"]
    sc = sc[sc["score"].notna()]
    top_clubs = topclub_liste(df, a.topclubs or defaults.get("topclubs", 20))
    ref = topclub_referenz(df, prof, defaults, top_clubs)
    sc = sc.assign(vs_topclub=vs_topclub(sc, prof, ref))

    if a.detail:
        hit = sc[sc["name"].fillna("").str.contains(a.detail, case=False)]
        if hit.empty:
            common.die(
                f"Kein Spieler mit '{a.detail}' im Profil {prof['name']} (Position/Minuten/Abdeckung)."
            )
        for _, r in hit.iterrows():
            print(
                f"\n{r['name']} ({r['club']}, {r['league']}, {r['age']}) Score {r['score']:.0f}, Daten: {r['datenbasis']}"
            )
            print(
                f"  vs. Topclub (Ø): {r['vs_topclub']:.0f}"
                if pd.notna(r["vs_topclub"])
                else "  vs. Topclub: keine Referenz"
            )
            for sp in prof["stats"]:
                v, s = r[f"v_{sp['stat']}"], r[f"s_{sp['stat']}"]
                if pd.isna(v):
                    print(f"  {sp['label']:36}    fehlt")
                    continue
                rf = ref.get(sp["stat"])
                top = (
                    f"  Topclub-Median {np.median(rf):.2f}, besser als "
                    f"{prozent_im_referenz(rf, [v], sp['schlecht'] > sp['gut'])[0]:.0f} %"
                    if rf is not None
                    else ""
                )
                print(
                    f"  {sp['label']:36} {v:8.2f}  [schlecht {sp['schlecht']} / ok {sp['ok']} / gut {sp['gut']}]  -> {s:.0f}{top}"
                )
        return

    if a.max_alter is not None:
        sc = sc[sc["age"] <= a.max_alter]
    if a.liga:
        sc = sc[sc["league"].fillna("").str.contains(a.liga, case=False)]
    lg = ligen.Ligen.laden(a.config_dir)
    schema = (
        a.gewichtung or prof.get("gewichtung") or lg.standard
    )  # Profil legt Angriff/Verteidigung fest
    sc = sc.assign(liga_stufe=sc["league"].map(lg.stufe))
    note = ""
    if a.min_stufe:
        try:
            limit = lg.stufe_index(a.min_stufe)
        except ValueError:
            common.die(f"Unbekannte Stufe '{a.min_stufe}'. Vorhanden: {', '.join(lg.stufen)}")
        sc = sc[sc["liga_stufe"].map(lambda x: isinstance(x, str) and lg.stufe_index(x) <= limit)]
    if schema != "aus":
        if schema not in lg.schemata():
            common.die(f"Unbekanntes Schema '{schema}'. Vorhanden: aus, {', '.join(lg.schemata())}")
        sc = sc.assign(liga_gewicht=lg.gewicht_spalte(sc, schema))  # je Saison (Saisonbasis)
        n_ohne = int(sc["liga_gewicht"].isna().sum())
        note = f"Gewichtung '{schema}'; {n_ohne} Spieler aus Ligen ohne Stufe ausgeblendet."
        sc = sc[sc["liga_gewicht"].notna()]
        sc = sc.assign(score_gew=sc["score"] * sc["liga_gewicht"])
    rank_col = "score_gew" if "score_gew" in sc else "score"
    sc = sc.assign(
        wert_mio=sc["value"] / 1e6,
        stats=sc["n_stats"].astype(int).astype(str) + "/" + str(len(prof["stats"])),
        minutes=per90.minuten_anzeige(sc),  # "2940 (VS, w=0,93) + 90", wenn die Vorsaison zählt
    )
    cols = [
        "name",
        "club",
        "league",
        "liga_stufe",
        "age",
        "minutes",
        "score",
        *(["score_gew"] if "score_gew" in sc else []),
        "vs_topclub",
        "stats",
        "spitze",
        "datenbasis",
        "wert_mio",
        "contract_end",
    ]
    if a.csv:
        sc.sort_values(rank_col, ascending=False)[cols].round(2).to_csv(a.csv, index=False)
        print(f"{len(sc)} Zeilen -> {a.csv}")
        return
    from tabulate import tabulate

    print(
        f"## {prof['name']} (Daten vom {df.attrs.get('date')}, min. {a.min_minuten or defaults.get('min_minuten', 900)} Min., "
        f"{anker_info})"
    )
    own = sc[sc["own"]].sort_values(rank_col, ascending=False)
    if len(own):
        print("\n### Eigene Spieler (Maßstab)")
        print(tabulate(own[cols].round(2), headers="keys", tablefmt="github", showindex=False))
    cand = sc[~sc["own"]].sort_values(rank_col, ascending=False).head(a.top)
    print(f"\n### Kandidaten (Top {a.top} von {int((~sc['own']).sum())})")
    print(tabulate(cand[cols].round(2), headers="keys", tablefmt="github", showindex=False))
    if note:
        print(f"\n{note} Sortiert nach score_gew = score x Liga-Gewicht.")
    print(
        "Score 0 = Schlecht, 50 = OK, 100 = Gut (Anker siehe Kopfzeile). Marktwert = gespeicherter Basiswert, nicht der angezeigte."
    )
    n_ref = max((len(v) for v in ref.values()), default=0)
    print(
        f"vs_topclub: Ø Anteil der Topclub-Spieler dieser Rolle (bis zu {n_ref}), den der Spieler pro Statistik übertrifft; "
        f"50 = Topclub-Median. Topclubs = Top {len(top_clubs)} nach Kaderwert: {', '.join(top_clubs)}."
    )


if __name__ == "__main__":
    main()
