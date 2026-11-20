"""Team-KPIs je Spiel, gleitend (5 Spiele), nach Heim/Auswärts und Taktik-Slot, Vorher/Nachher.

Aufruf:  uv run python scripts/team.py --save werder [--ab 2027-02-01] [--letzte 15]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KPI_CANDIDATES = [
    "xg_for",
    "xg_against",
    "goals_for",
    "goals_against",
    "shots_for",
    "shots_against",
    "possession",
]


def load_matches(conn, save: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT * FROM team_matches WHERE save=? ORDER BY ingame_date, id", conn, params=[save]
    )
    df["ingame_date"] = pd.to_datetime(df["ingame_date"])
    if {"xg_for", "xg_against"} <= set(df.columns):
        df["xg_diff"] = df["xg_for"] - df["xg_against"]
    return df


def kpi_columns(df: pd.DataFrame) -> list[str]:
    cols = [c for c in KPI_CANDIDATES + ["xg_diff"] if c in df and df[c].notna().any()]
    return cols


def rolling(df: pd.DataFrame, kpis: list[str], window: int = 5) -> pd.DataFrame:
    out = df[["ingame_date", "opponent", "home_away", "tactic_slot"] + kpis].copy()
    for k in kpis:
        out[f"{k}_roll{window}"] = df[k].rolling(window, min_periods=window).mean()
    return out


def summarize(df: pd.DataFrame, kpis: list[str], by: str) -> pd.DataFrame:
    g = df.groupby(by, dropna=False)[kpis].mean()
    g.insert(0, "spiele", df.groupby(by, dropna=False).size())
    return g


def before_after(df: pd.DataFrame, kpis: list[str], ab: str) -> pd.DataFrame:
    cut = pd.Timestamp(ab)
    vor, nach = df[df["ingame_date"] < cut], df[df["ingame_date"] >= cut]
    out = pd.DataFrame({"vorher": vor[kpis].mean(), "nachher": nach[kpis].mean()})
    out["delta"] = out["nachher"] - out["vorher"]
    out.loc["spiele"] = [len(vor), len(nach), float("nan")]
    return out


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    common.add_common_args(ap)
    ap.add_argument("--ab", help="In-Game-Datum (YYYY-MM-DD) für Vorher/Nachher-Vergleich")
    ap.add_argument("--fenster", type=int, default=5, help="Fenster für gleitenden Schnitt")
    ap.add_argument(
        "--letzte", type=int, default=10, help="Anzahl Spiele in der Einzelspiel-Tabelle"
    )
    a = ap.parse_args(argv)

    save = common.resolve_save(a.save)
    df = load_matches(common.connect(a.db), save)
    if df.empty:
        common.die(f"Keine Spiele für Save '{save}' – Export 'spiel'/'team_stats' importieren.")
    kpis = kpi_columns(df)
    if not kpis:
        common.die(
            "team_matches enthält keine KPI-Werte (spalten.yaml: xg_for, xg_against, … mappen)."
        )

    from tabulate import tabulate

    def show(title: str, table: pd.DataFrame, index: bool = False) -> None:
        print(f"\n## {title}\n")
        print(tabulate(table.round(2), headers="keys", tablefmt="github", showindex=index))

    show(
        f"Letzte {a.letzte} Spiele (gleitend {a.fenster})",
        rolling(df, kpis, a.fenster)
        .tail(a.letzte)
        .assign(ingame_date=lambda d: d["ingame_date"].dt.date),
    )
    show("Heim / Auswärts", summarize(df.fillna({"home_away": "?"}), kpis, "home_away"), index=True)
    show("Taktik-Slot", summarize(df.fillna({"tactic_slot": "?"}), kpis, "tactic_slot"), index=True)
    if a.ab:
        show(f"Vorher / Nachher ab {a.ab}", before_after(df, kpis, a.ab), index=True)


if __name__ == "__main__":
    main()
