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

CORE_COLS = [
    "player_uid",
    "name",
    "club",
    "league",
    "club_country",
    "position",
    "age",
    "wage",
    "wage_min",
    "wage_max",
    "value",
    "contract_end",
    "loan_end",
    "value_min",
    "value_max",
    "minutes",
    "team_possession",
    "ingame_date",
    "snapshot_id",
    "birthdate",
]


def load_wide(conn, save: str, view: str | None = None):
    """Neuester Snapshot je Spieler. -> (players+Stats-Spalten, Attribute-Spalten `attr_*`)."""
    q = (
        "SELECT p.*, s.ingame_date, s.view_type FROM players p "
        "JOIN snapshots s ON s.id = p.snapshot_id WHERE s.save = ?"
    )
    args: list = [save]
    if view:
        q += " AND s.view_type = ?"
        args.append(view)
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


def position_matches(pos, positions) -> bool:
    """TODO(export): Positionsformat prüfen. Erwartet z. B. 'ST', 'ST (C)', 'AM (RLC), ST (C)'."""
    if not isinstance(pos, str):
        return False
    wanted = {p.upper() for p in positions}
    tokens = [t.strip().split()[0].upper() for t in pos.replace("/", ",").split(",") if t.strip()]
    return any(t in wanted for t in tokens)


def percentile_in_groups(df: pd.DataFrame, col: str, pool: pd.Series, min_group: int) -> pd.Series:
    """Perzentil (0-100) von `col` innerhalb Position+Liga, nur Spieler im `pool` zählen mit."""
    out = pd.Series(np.nan, index=df.index)
    sub = df[pool].copy()
    pos = sub["position"].fillna("?").astype(str).str.split(r"[,/]").str[0].str.split().str[0]
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
    players, _ = load_wide(common.connect(a.db), save, a.view)
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
