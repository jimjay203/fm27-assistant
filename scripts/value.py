"""Rollen-Score, Kosten pro Saison, Value-Score und xG-Delta.

Rollen-Score  = gewichtete Summe der KPI-Perzentile (rollen.yaml), optional gemischt mit einem
                Attribut-Prior (Perzentile der Attribute; Anteil = attribut_gewicht).
Kosten/Saison = Jahresgehalt + Marktwert / Vertragsjahre (min. 1 Jahr). TODO: Ablöse, falls im Export.
Value-Score   = Perzentil von Rollen-Score / Kosten (in Mio) unter den gefilterten Kandidaten.
xG-Delta      = Tore - xG bzw. Assists - xA (Stat-Namen `tore`, `xg`, `assists`, `xa`; TODO(export)).

Fair Value (scripts/fairvalue.py): erwarteter FM-Marktwert für Leistung/Alter/Liga/Restlaufzeit;
`fv_ratio` > 1 = FM bewertet den Spieler niedriger als im Pool üblich. R² und n stehen auf stderr.

Aufruf:  uv run python scripts/value.py --rolle stuermer_abschluss --max-alter 31 --top 20
         uv run python scripts/value.py --rolle gruppe_st --sort fv --nur-moneyball
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fairvalue
import per90


def role_score(df: pd.DataFrame, kpis: dict[str, float], min_cover: float = 1.0) -> pd.Series:
    """Gewichtete KPI-Perzentile über die vorhandenen KPIs.

    NaN, wenn weniger als `min_cover` des Gewichts vorliegt. Default 1.0 = strikt (jeder KPI muss
    da sein, keine stille Lücke); kleinere Werte tolerieren fehlende KPIs (reduzierte Ligadaten)."""
    total = sum(kpis.values())
    num = pd.Series(0.0, index=df.index)
    have = pd.Series(0.0, index=df.index)
    for k, w in kpis.items():
        pct = df[f"{k}_pctl"]
        num = num + pct.fillna(0) * w
        have = have + pct.notna() * w
    score = num / have.where(have > 0)
    return score.where(have >= min_cover * total - 1e-9)


def attribute_score(
    df: pd.DataFrame, attrs: pd.DataFrame, prior: dict[str, float], pool: pd.Series, min_group: int
) -> pd.Series:
    """Gewichtetes Mittel der Attribut-Perzentile (maskierte Werte zählen nicht mit)."""
    merged = df[["player_uid", "snapshot_id", "position", "league", "club_country"]].merge(
        attrs, on=["snapshot_id", "player_uid"], how="left"
    )
    merged.index = df.index
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for attr, w in prior.items():
        col = f"attr_{attr}"
        if col not in merged:
            continue
        pct = per90.percentile_in_groups(merged, col, pool & merged[col].notna(), min_group)
        num += pct.fillna(0) * w
        den += pct.notna() * w
    return num / den.where(den > 0)


def season_cost(df: pd.DataFrame) -> pd.Series:
    end = pd.to_datetime(df["contract_end"], errors="coerce")
    now = pd.to_datetime(df["ingame_date"], errors="coerce")
    years = ((end - now).dt.days / 365.25).clip(lower=1.0)
    return df["wage"] + df["value"] / years


def xg_deltas(df: pd.DataFrame, flag_p90: float) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    m = df["minutes"].astype(float).where(df["minutes"] > 0)
    for tag, got, exp in (("xg_delta", "tore", "xg"), ("xa_delta", "assists", "xa")):
        out[tag] = (df[got] - df[exp]) if got in df and exp in df else np.nan
        out[f"{tag}_p90"] = out[tag] / m * 90
    flag = pd.Series("", index=df.index)
    flag[out["xg_delta_p90"] >= flag_p90] = "über xG"
    flag[out["xg_delta_p90"] <= -flag_p90] = "unter xG"
    out["xg_flag"] = flag
    return out


def candidates(
    players,
    attrs,
    cfg,
    rolle,
    *,
    max_alter=None,
    max_kosten=None,
    liga=None,
    land=None,
    min_minuten=None,
    attr_gewicht=None,
    leagues: dict | None = None,
) -> pd.DataFrame:
    defaults = cfg.get("defaults", {})
    role = (cfg.get("rollen") or {}).get(rolle)
    if role is None:
        common.die(f"Rolle '{rolle}' nicht in config/rollen.yaml")
    df = per90.compute_per90(players, cfg, rolle, min_minuten)
    missing = [k for k in role["kpis"] if f"{k}_pctl" not in df]
    if missing:
        common.die(
            "Für die Rolle fehlen KPIs in den Daten (Export/spalten.yaml ergänzen): "
            + ", ".join(missing)
        )
    threshold = df.attrs["min_minuten"]
    n_total = len(df)
    df = df[~df["n_klein"]].copy()
    print(
        f"{n_total - len(df)} von {n_total} Spielern ausgeschlossen (n<{threshold} Minuten).",
        file=sys.stderr,
    )

    min_cover = role.get("min_abdeckung", defaults.get("min_abdeckung", 1.0))
    df["kpi_score"] = role_score(df, role["kpis"], min_cover)
    g = defaults.get("attribut_gewicht", 0.0) if attr_gewicht is None else attr_gewicht
    df["attr_score"] = np.nan
    df["rollen_score"] = df["kpi_score"]
    if g > 0 and role.get("attribute_prior"):
        pool = pd.Series(True, index=df.index)
        df["attr_score"] = attribute_score(
            df, attrs, role["attribute_prior"], pool, defaults.get("min_gruppe", 5)
        )
        df["rollen_score"] = np.where(
            df["attr_score"].notna(),
            (1 - g) * df["kpi_score"] + g * df["attr_score"],
            df["kpi_score"],
        )
    if leagues:
        strength = df["league"].map(leagues)
        df["rollen_score"] = df["rollen_score"] * strength / strength.mean()

    df["kosten_saison"] = season_cost(df)
    df = pd.concat([df, xg_deltas(df, defaults.get("xg_delta_flag_p90", 0.10))], axis=1)
    # Fair Value auf dem vollen Rollenpool, bevor Alter/Liga/Land filtern (sonst Fit auf Ausschnitt).
    df, fv = fairvalue.add_fair_value(df, players, defaults)
    print(
        f"Fair Value ({rolle}): n={fv['n']}, "
        + (f"R²={fv['r2']:.2f}, Streuung x{10 ** fv['rmse']:.1f}" if fv["ok"] else f"nicht berechnet ({fv['grund']})"),
        file=sys.stderr,
    )

    if max_alter is not None:
        df = df[df["age"] <= max_alter]
    if max_kosten is not None:
        df = df[df["kosten_saison"] <= max_kosten]
    if liga:
        df = df[df["league"] == liga]
    if land:
        df = df[df["club_country"] == land]
    df = df.copy()
    ratio = df["rollen_score"] / (df["kosten_saison"].where(df["kosten_saison"] > 0) / 1e6)
    df["value_pctl"] = ratio.rank(pct=True) * 100
    return df


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--rolle", required=True)
    ap.add_argument("--view", choices=common.PLAYER_VIEWS)
    ap.add_argument("--max-alter", type=int)
    ap.add_argument("--max-kosten", type=float, help="Kosten pro Saison in Euro")
    ap.add_argument("--liga")
    ap.add_argument("--land", help="Land des Vereins (Spalte 'Ansässig in'), z. B. 'Österreich'")
    ap.add_argument("--min-minuten", type=int)
    ap.add_argument(
        "--attr-gewicht", type=float, help="Anteil Attribut-Prior 0..1 (Default: rollen.yaml)"
    )
    ap.add_argument(
        "--liga-norm",
        action="store_true",
        help="Rollen-Score mit Liga-Stärke skalieren (Tabelle leagues; Hypothese, ungeprüft)",
    )
    ap.add_argument("--sort", choices=["value", "rolle", "fv"], default="value")
    ap.add_argument(
        "--nur-moneyball",
        action="store_true",
        help="Nur Spieler über fv_ratio_min, fv_z_min und fv_min_fair (rollen.yaml)",
    )
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args(argv)

    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    players, attrs = per90.load_wide(conn, save, a.view)
    if players.empty:
        common.die(f"Keine Spielerdaten für Save '{save}' – erst scripts/import.py ausführen.")
    leagues = None
    if a.liga_norm:
        leagues = dict(
            conn.execute("SELECT league, reputation_or_strength FROM leagues").fetchall()
        )
        if not leagues:
            common.die("--liga-norm: Tabelle leagues leer (config/ligen.yaml – offener Punkt 5).")
    cfg = common.load_yaml("rollen.yaml", a.config_dir)
    df = candidates(
        players,
        attrs,
        cfg,
        a.rolle,
        max_alter=a.max_alter,
        max_kosten=a.max_kosten,
        liga=a.liga,
        land=a.land,
        min_minuten=a.min_minuten,
        attr_gewicht=a.attr_gewicht,
        leagues=leagues,
    )
    if a.nur_moneyball:
        df = df[df["moneyball"]]
    sort_col = {"value": "value_pctl", "rolle": "rollen_score", "fv": "fv_ratio"}[a.sort]
    df = df.sort_values(sort_col, ascending=False)
    df["kosten_mio"] = df["kosten_saison"] / 1e6
    df["fair_value_mio"] = df["fair_value"] / 1e6
    out = df[
        [
            "name",
            "club",
            "league",
            "club_country",
            "liga_rang",
            "position",
            "age",
            "minutes",
            "rollen_score",
            "kosten_mio",
            "value_pctl",
            "fair_value_mio",
            "fv_ratio",
            "fv_z",
            "moneyball",
            "xg_delta",
            "xg_flag",
            "xa_delta",
        ]
    ].round(2)
    out = out.head(a.top) if not a.csv else out
    if a.csv:
        out.to_csv(a.csv, index=False)
        print(f"{len(out)} Zeilen -> {a.csv}")
    else:
        from tabulate import tabulate

        print(tabulate(out, headers="keys", tablefmt="github", showindex=False))


if __name__ == "__main__":
    main()
