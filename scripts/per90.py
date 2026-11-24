"""Per-90-Werte, Ballbesitzbereinigung und Perzentile (je Position + Liga).

Namenskonvention der Stats (spalten.yaml): Zählstat `x` -> Spalte `x_p90`; `x_pct` (Rate), `x_p90`
(schon pro 90), `x_avg` (Durchschnitt) und `x_n` (Spielezähler) bleiben unverändert. Perzentile
erhalten das Suffix `_pctl`.

Aufruf:  uv run python scripts/per90.py --rolle stuermer_abschluss [--csv out.csv]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

# Stats mit diesen Suffixen werden nicht durch Minuten geteilt (Rate, Durchschnitt, Spielezähler).
NOT_NORMALIZED = ("_pct", "_p90", "_avg", "_n")

# Deutsche Positionskürzel der Exporte -> englische (FMMT-Live, rollen.yaml). Gleiche Kürzel (ST, DM, M)
# brauchen keinen Eintrag. FV = Flügel-/Außenverteidiger (hier WB), OM = offensives Mittelfeld (AM).
POS_ALIAS = {"TW": "GK", "V": "D", "FV": "WB", "OM": "AM"}

CORE_COLS = [
    "player_uid",
    "name",
    "club",
    "league",
    "club_country",
    "liga_rang",
    "liga_ansehen",
    "position",
    "age",
    "wage",
    "wage_min",
    "wage_max",
    "value",
    "contract_end",
    "loan_end",
    "loan_start",
    "value_min",
    "value_max",
    "minutes",
    "team_possession",
    "ingame_date",
    "snapshot_id",
    "birthdate",
]


def letzter_snapshot(conn, save: str, view: str) -> tuple[int, str] | None:
    """(id, ingame_date) des neuesten Snapshots dieses Typs, sonst None."""
    r = conn.execute(
        "SELECT id, ingame_date FROM snapshots WHERE save = ? AND view_type = ? "
        "ORDER BY ingame_date DESC, id DESC LIMIT 1",
        (save, view),
    ).fetchone()
    return (int(r[0]), r[1]) if r else None


def letzte_snapshots(conn, save: str, views=("kader", "suche", "live")) -> dict[str, tuple[int, str]]:
    """Je Typ nur der neueste Snapshot: ältere Suchen haben veraltete Saisonstatistiken."""
    return {v: s for v in views if (s := letzter_snapshot(conn, save, v))}


def load_wide(conn, save: str, view: str | None = None, snapshot_ids: list[int] | None = None):
    """Neuester Snapshot je Spieler. -> (players+Stats-Spalten, Attribute-Spalten `attr_*`).

    `snapshot_ids` beschränkt auf diese Snapshots (z. B. nur den letzten Kader und die letzte Suche)."""
    q = (
        "SELECT p.*, s.ingame_date, s.view_type, lr.rang AS liga_rang, lr.ansehen AS liga_ansehen "
        "FROM players p JOIN snapshots s ON s.id = p.snapshot_id "
        "LEFT JOIN league_ranking lr ON lr.league = p.league AND lr.country = p.club_country "
        "WHERE s.save = ?"
    )
    args: list = [save]
    if view:
        q += " AND s.view_type = ?"
        args.append(view)
    if snapshot_ids is not None:
        if not snapshot_ids:
            empty = pd.DataFrame(columns=["snapshot_id", "player_uid"])
            return empty, empty.copy()
        q += f" AND s.id IN ({','.join('?' * len(snapshot_ids))})"
        args.extend(int(i) for i in snapshot_ids)
    players = pd.read_sql_query(q + " ORDER BY s.ingame_date, s.id", conn, params=args)
    players = players.drop_duplicates("player_uid", keep="last").reset_index(drop=True)
    if players.empty:
        return players, players.copy()
    keys = players[["snapshot_id", "player_uid"]]
    stats = pd.read_sql_query("SELECT * FROM player_stats", conn)
    stats = stats.merge(keys, on=["snapshot_id", "player_uid"])
    stats = stats.pivot_table(
        index=["snapshot_id", "player_uid"], columns="stat", values="value", aggfunc="last"
    ).reset_index()
    attrs = pd.read_sql_query("SELECT * FROM player_attributes", conn)
    attrs = attrs.merge(keys, on=["snapshot_id", "player_uid"])
    attrs = (
        attrs.pivot_table(
            index=["snapshot_id", "player_uid"],
            columns="attribute",
            values="value",
            aggfunc="last",
            dropna=False,
        ).reset_index()
        if not attrs.empty
        else keys.copy()
    )
    attrs = attrs.rename(
        columns={c: f"attr_{c}" for c in attrs.columns if c not in ("snapshot_id", "player_uid")}
    )
    players = players.merge(stats, on=["snapshot_id", "player_uid"], how="left")
    return players, attrs


# --------------------------------------------------------------------------- Saisonbasis (config/saison.yaml)
# Entscheidung Jimmy (in-game 07.07.2027): Per-90-Basis = Vorsaison + laufende Saison je Spieler (player_uid).
# Je Saison und Quelle gilt der letzte Snapshot der Saison; Gewicht der Vorsaison w = max(0, 1 - Min_neu/Übergang).

SAISON_VIEWS = ("kader", "suche", "live")
# Spalten, die weder Kernfeld (CORE_COLS) noch Statistik sind (Exporte, Live-Reader, Planer)
# Zusatzspalten der Saisonbasis (kombinieren): keine Statistiken
SAISON_SPALTEN = ("min_neu", "min_vs", "w_vs", "min_vs_w", "league_vs", "club_vs", "minuten_text")
NICHT_STATS = {"view_type", "uid", "own", "eigen", "team", "datenbasis", "in_suche", "quelle",
               *SAISON_SPALTEN}  # fmt: skip
RATEN = ("_pct", "_avg", "_p90")  # minutengewichtet; alles andere (auch _n) sind Zählwerte
RATEN_KERN = ("team_possession",)  # Kernfeld, das wie eine Rate kombiniert wird


def saison_cfg(config_dir=None) -> dict:
    cfg = common.load_yaml("saison.yaml", config_dir) or {}
    return {
        "grenze": str(cfg.get("saison_grenze", "07-01")),
        "uebergang": float(cfg.get("saison_uebergang_minuten", 1200)),
    }


def saison_von(datum, grenze: str = "07-01") -> str | None:
    """In-Game-Datum -> Saison: '2027-05-31' -> '2026/27', '2027-07-01' -> '2027/28' (Grenze MM-TT)."""
    s = str(datum or "")[:10]
    if len(s) < 10 or not s[:4].isdigit():
        return None
    start = int(s[:4]) if s[5:] >= grenze else int(s[:4]) - 1
    return f"{start}/{(start + 1) % 100:02d}"


def vorsaison(saison: str) -> str:
    start = int(saison[:4]) - 1
    return f"{start}/{(start + 1) % 100:02d}"


def saison_snapshots(conn, save: str, views=SAISON_VIEWS, grenze: str = "07-01") -> dict:
    """{saison: {view: (id, datum)}}: je Saison und Quelle der letzte Snapshot (Datum, dann id)."""
    out: dict[str, dict[str, tuple[int, str]]] = {}
    q = (
        "SELECT id, ingame_date, view_type FROM snapshots WHERE save = ? AND view_type IN "
        f"({','.join('?' * len(views))}) ORDER BY ingame_date, id"
    )
    for sid, d, v in conn.execute(q, [save, *views]):
        if (sz := saison_von(d, grenze)) is not None:
            out.setdefault(sz, {})[v] = (int(sid), d)
    return out


def _stat_spalten(df: pd.DataFrame) -> list[str]:
    return [
        c for c in df.columns
        if (c not in CORE_COLS or c in RATEN_KERN) and c not in NICHT_STATS and not str(c).startswith("attr_")
        and not str(c).endswith("_pctl") and pd.api.types.is_numeric_dtype(df[c])
    ]  # fmt: skip


def _minuten_text(m_vs: float, w: float, m_neu: float) -> str:
    return f"{m_vs:.0f} (VS, w={w:.2f}) + {m_neu:.0f}".replace(".", ",")


def kombinieren(
    neu: pd.DataFrame, alt: pd.DataFrame | None, uebergang: float = 1200.0, key: str = "player_uid",
    nur_neu: bool = False,
) -> pd.DataFrame:  # fmt: skip
    """Laufende Saison (`neu`) und Vorsaison (`alt`) je Spieler zu einer Per-90-Basis zusammenführen.

    w = max(0, 1 - Minuten_neu / uebergang). Minuten = Minuten_VS x w + Minuten_neu. Zählwerte: VS x w + neu,
    hochgerechnet auf alle Minuten, wenn eine Saison die Statistik nicht hat (z. B. Liga ohne Laufdaten); Raten
    (_pct, _avg, _p90, Ballbesitz) minutengewichtet. Kernfelder (Verein, Liga, Marktwert, Gehalt, Vertrag, Alter,
    Snapshot) vom neuesten Stand: neue Saison, sonst Vorsaison. Spieler nur in der Vorsaison bleiben (außer
    `nur_neu`, z. B. live: dort fehlt nur, wer nicht mehr im Spiel ist). Zusatzspalten: min_neu, min_vs, w_vs,
    min_vs_w, league_vs (Liga der Vorsaison, mit Land), club_vs und minuten_text, z. B. "2940 (VS, w=0,93) + 90"."""
    import ligen  # erst hier: ligen importiert common, per90 wird von vielen Modulen geladen

    n = neu.drop_duplicates(key, keep="last").set_index(key)
    a = None
    if alt is not None and len(alt):
        a = alt.drop_duplicates(key, keep="last").set_index(key)
    if a is not None and nur_neu:
        a = a[a.index.isin(n.index)]
    if a is None or a.empty:
        out = n.copy()
        mins = pd.to_numeric(out["minutes"], errors="coerce") if "minutes" in out else np.nan
        out = out.assign(
            min_neu=mins, min_vs=np.nan, w_vs=np.nan, min_vs_w=np.nan, league_vs=None, club_vs=None
        )
        out["minuten_text"] = [None if pd.isna(m) else f"{m:.0f}" for m in out["min_neu"]]
        return out.reset_index()
    basis = pd.concat([n, a[~a.index.isin(n.index)]])
    idx = basis.index

    def spalte(df, c):
        return (
            pd.to_numeric(df[c], errors="coerce").reindex(idx).astype(float)
            if c in df else pd.Series(np.nan, index=idx)
        )  # fmt: skip

    roh_neu, roh_vs = spalte(n, "minutes"), spalte(a, "minutes")
    m_neu, m_vs = roh_neu.fillna(0.0), roh_vs.fillna(0.0)
    hat_vs = pd.Series(idx.isin(a.index), index=idx)
    w = (1 - m_neu / uebergang).clip(lower=0.0)
    mw = m_vs * w
    gesamt = mw + m_neu
    werte = {}
    for c in dict.fromkeys(_stat_spalten(n) + _stat_spalten(a)):
        xn, xa = spalte(n, c), spalte(a, c)
        gn, ga = m_neu.where(xn.notna(), 0.0), mw.where(xa.notna(), 0.0)
        g = gn + ga
        # nur eine Saison mit Minuten: deren Wert unverändert (keine Rundungsfehler, gleiche Perzentil-Ränge)
        if str(c).endswith(RATEN) or c in RATEN_KERN:
            wert = (xn.fillna(0) * gn + xa.fillna(0) * ga) / g.where(g > 0)
            wert = wert.where(gn > 0, xa).where(ga > 0, xn)
            ersatz = xn.where(xn.notna(), xa.where(w > 0))
        else:
            summe = xn.fillna(0) + xa.fillna(0) * w
            wert = summe * (gesamt / g.where(g > 0))
            wert = wert.where(gn > 0, xa * w * (gesamt / g.where(g > 0)))
            wert = wert.where(~((gn <= 0) & (w == 1) & (gesamt == ga)), xa)
            ersatz = summe.where(xn.notna() | (xa.notna() & (w > 0)))
        # ohne Minutenbasis (keine Minuten in einer Saison mit der Statistik): nur ohne Minuten insgesamt übernehmen
        werte[c] = wert.where(g > 0, ersatz.where(gesamt <= 0))
    out = basis.drop(columns=[c for c in werte if c in basis])
    out = pd.concat([out, pd.DataFrame(werte, index=idx)], axis=1)
    out["minutes"] = gesamt.where(roh_neu.notna() | roh_vs.notna())
    out["min_neu"], out["min_vs"] = m_neu, m_vs.where(hat_vs)
    out["w_vs"], out["min_vs_w"] = w.where(hat_vs), mw.where(hat_vs)
    liga_vs = ligen.mit_land(a) if "league" in a else pd.Series(None, index=a.index)
    out["league_vs"] = liga_vs.reindex(idx)
    out["club_vs"] = a["club"].reindex(idx) if "club" in a else None
    out["minuten_text"] = [
        _minuten_text(v, ww, nn) if h and v > 0 else (None if pd.isna(m) else f"{m:.0f}")
        for h, v, ww, nn, m in zip(hat_vs, m_vs, w, m_neu, out["minutes"], strict=True)
    ]
    return out.reset_index()


def saison_info(aktuell: str, vs: str, ids_neu: dict, ids_vs: dict, uebergang: float) -> dict:
    return {"aktuell": aktuell, "vorsaison": vs, "neu": dict(ids_neu), "vs": dict(ids_vs),
            "uebergang": uebergang}  # fmt: skip


def load_saison(conn, save: str, views=SAISON_VIEWS, config_dir=None):
    """Wie load_wide, aber mit Saisonbasis: je Quelle der letzte Snapshot der laufenden Saison und der Vorsaison,
    kombiniert mit kombinieren(). Laufende Saison = Saison des neuesten Snapshots dieser Quellen.
    -> (players, attrs); players.attrs["saison"] = aktuell, vorsaison, Snapshots je Quelle, Übergang."""
    sc = saison_cfg(config_dir)
    snaps = saison_snapshots(conn, save, views, sc["grenze"])
    if not snaps:
        return load_wide(conn, save, snapshot_ids=[])
    aktuell = max(snaps)
    vs = vorsaison(aktuell)
    ids_neu, ids_vs = snaps.get(aktuell, {}), snaps.get(vs, {})
    neu, attrs_neu = load_wide(conn, save, snapshot_ids=[i for i, _ in ids_neu.values()])
    alt, attrs_alt = load_wide(conn, save, snapshot_ids=[i for i, _ in ids_vs.values()])
    df = kombinieren(neu, alt, sc["uebergang"])
    keys = df[["snapshot_id", "player_uid"]]
    attrs = pd.concat([attrs_neu, attrs_alt], ignore_index=True).merge(
        keys, on=["snapshot_id", "player_uid"]
    )
    df.attrs["saison"] = saison_info(aktuell, vs, ids_neu, ids_vs, sc["uebergang"])
    return df, attrs


def mit_vorsaison(conn, save: str, neu: pd.DataFrame, stichtag, views=SAISON_VIEWS,
                  config_dir=None, key: str = "uid") -> pd.DataFrame:  # fmt: skip
    """Live-Daten (laufende Saison am `stichtag`) mit der Vorsaison aus der DB kombinieren (nur Spieler, die live
    vorkommen). Ohne Vorsaison-Snapshot bleiben die Live-Werte unverändert (plus Zusatzspalten)."""
    sc = saison_cfg(config_dir)
    aktuell = saison_von(stichtag, sc["grenze"])
    attrs = dict(neu.attrs)
    if aktuell is None:
        out = kombinieren(neu, None, sc["uebergang"], key=key)
        out.attrs = attrs
        return out
    vs = vorsaison(aktuell)
    ids_vs = saison_snapshots(conn, save, views, sc["grenze"]).get(vs, {})
    alt, _ = load_wide(conn, save, snapshot_ids=[i for i, _ in ids_vs.values()])
    alt = alt.rename(columns={"player_uid": key})
    out = kombinieren(neu, alt, sc["uebergang"], key=key, nur_neu=True)
    info = saison_info(aktuell, vs, {"live": (None, stichtag)}, ids_vs, sc["uebergang"])
    out.attrs = {**attrs, "saison": info}
    return out


def saison_text(info: dict | None) -> str:
    """Kurzbeschreibung der Saisonbasis, z. B. für Kopfzeilen: Saisons, Snapshots je Quelle, Übergang."""
    if not info:
        return "Saisonbasis: keine Angabe"

    def snaps(d: dict) -> str:
        teile = [f"{v} {s[1]}" + (f" #{s[0]}" if s[0] is not None else "") for v, s in d.items()]
        return ", ".join(teile) or "-"

    vs = f"Vorsaison {info['vorsaison']}: {snaps(info['vs'])}" if info.get("vs") else (
        f"keine Vorsaison {info['vorsaison']}")  # fmt: skip
    return (
        f"Saisonbasis {info['aktuell']}: {snaps(info['neu'])}; {vs}; "
        f"w = max(0, 1 - Min. neu / {info['uebergang']:.0f})"
    )


def minuten_anzeige(df: pd.DataFrame) -> pd.Series:
    """Minuten für Tabellen: "2940 (VS, w=0,93) + 90", wenn die Vorsaison zählt, sonst die Minuten."""
    if "minuten_text" not in df:
        return df["minutes"]
    return df["minuten_text"].where(df["minuten_text"].notna(), df["minutes"])


def position_matches(pos, positions) -> bool:
    """TODO(export): Positionsformat prüfen. Erwartet z. B. 'ST', 'ST (C)', 'AM (RLC), ST (C)'."""
    if not isinstance(pos, str):
        return False
    wanted = {p.upper() for p in positions}
    tokens = [t.strip().split()[0].upper() for t in pos.replace("/", ",").split(",") if t.strip()]
    return any(POS_ALIAS.get(t, t) in wanted for t in tokens)


def percentile_in_groups(df: pd.DataFrame, col: str, pool: pd.Series, min_group: int) -> pd.Series:
    """Perzentil (0-100) von `col` innerhalb Position+Liga, nur Spieler im `pool` zählen mit."""
    out = pd.Series(np.nan, index=df.index)
    sub = df[pool].copy()
    pos = sub["position"].fillna("?").astype(str).str.split(r"[,/]").str[0].str.split().str[0]
    pos = pos.replace(POS_ALIAS)  # Export (V, FV, OM, TW) und Live (D, WB, AM, GK) in dieselbe Gruppe
    # Liga + Land des Vereins: "Bundesliga" gibt es in Deutschland und Österreich.
    country = sub["club_country"].fillna("?") if "club_country" in sub else "?"
    keys = [pos, sub["league"].fillna("?"), country]
    grp = sub.groupby(keys, dropna=False)[col]
    pct = grp.rank(pct=True) * 100
    size = grp.transform("count")
    pct[size < min_group] = np.nan
    out.loc[pct.index] = pct
    return out


def compute_per90(
    df: pd.DataFrame,
    cfg: dict,
    rolle: str | None = None,
    min_minuten: int | None = None,
    stat_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Fügt `<stat>_p90`/`_pct`-Spalten, `n_klein`, `poss_fehlt` und `<kpi>_pctl` hinzu."""
    defaults = cfg.get("defaults", {})
    role = (cfg.get("rollen") or {}).get(rolle) if rolle else None
    if rolle and role is None:
        common.die(f"Rolle '{rolle}' nicht in config/rollen.yaml")
    threshold = (
        min_minuten
        if min_minuten is not None
        else (role or {}).get("min_minuten", defaults.get("min_minuten", 900))
    )
    min_group = defaults.get("min_gruppe", 5)
    defensiv = set(defaults.get("defensiv_volumen") or [])

    df = df.copy()
    if role:
        df = df[df["position"].apply(lambda p: position_matches(p, role["positionen"]))].copy()
    if stat_cols is None:
        stat_cols = [
            c
            for c in df.columns
            if c not in CORE_COLS
            and c != "view_type"
            and c not in SAISON_SPALTEN
            and not c.startswith("attr_")
            and not c.endswith("_pctl")
        ]
    minutes = df["minutes"].astype(float)
    df["n_klein"] = ~(minutes >= threshold)
    df["poss_fehlt"] = False
    kpis = []
    for c in stat_cols:
        if c.endswith(NOT_NORMALIZED):
            name, vals = c, df[c].astype(float)
        else:
            name = f"{c}_p90"
            vals = df[c].astype(float) / minutes.where(minutes > 0) * 90
            if c in defensiv:
                poss = df["team_possession"].astype(float)
                df.loc[poss.isna() | (poss <= 0), "poss_fehlt"] = True
                vals = vals.where(poss.isna() | (poss <= 0), vals * 50 / poss)
        if name != c:
            df[name] = vals
        kpis.append(name)
    pool = ~df["n_klein"]
    pctl = {f"{k}_pctl": percentile_in_groups(df, k, pool, min_group) for k in kpis}
    df = pd.concat([df, pd.DataFrame(pctl, index=df.index)], axis=1)
    df.attrs["kpis"] = kpis
    df.attrs["min_minuten"] = threshold
    return df


def format_table(df: pd.DataFrame, kpis: list[str], threshold: int) -> pd.DataFrame:
    cols = (
        ["name", "club", "league", "club_country", "position", "age", "minutes"]
        + [c for k in kpis for c in (k, f"{k}_pctl")]
        + ["n_klein", "poss_fehlt"]
    )
    out = df[[c for c in cols if c in df.columns]].copy()
    out["minutes"] = minuten_anzeige(df)
    out["n_klein"] = out["n_klein"].map({True: f"n<{threshold}", False: ""})
    out["poss_fehlt"] = out["poss_fehlt"].map({True: "Ballbesitz fehlt", False: ""})
    return out.round(2)


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument(
        "--rolle", help="Rolle aus rollen.yaml (filtert Positionen, setzt Mindestminuten)"
    )
    ap.add_argument("--view", choices=common.PLAYER_VIEWS, help="Nur Snapshots dieses Typs")
    ap.add_argument("--min-minuten", type=int)
    ap.add_argument("--csv", type=Path, help="Ausgabe als CSV statt Tabelle")
    a = ap.parse_args(argv)

    save = common.resolve_save(a.save)
    cfg = common.load_yaml("rollen.yaml", a.config_dir)
    views = (a.view,) if a.view else SAISON_VIEWS
    players, _ = load_saison(common.connect(a.db), save, views, a.config_dir)
    if players.empty:
        common.die(f"Keine Spielerdaten für Save '{save}' – erst scripts/import.py ausführen.")
    res = compute_per90(players, cfg, a.rolle, a.min_minuten)
    table = format_table(res, res.attrs["kpis"], res.attrs["min_minuten"])
    if a.csv:
        table.to_csv(a.csv, index=False)
        print(f"{len(table)} Zeilen -> {a.csv}")
    else:
        from tabulate import tabulate

        print(tabulate(table, headers="keys", tablefmt="github", showindex=False))
        print(
            f"\nMindestminuten: {res.attrs['min_minuten']}; Perzentile nur innerhalb Position+Liga "
            f"(Gruppen < {cfg.get('defaults', {}).get('min_gruppe', 5)} -> leer)."
        )


if __name__ == "__main__":
    main()
