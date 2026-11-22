"""Fair Value: was FM für diese Leistung typischerweise als Marktwert ansetzt (Moneyball-Filter).

Idee nach FMMT-27 (dort `valueModel`), hier neu umgesetzt:
  log10(Marktwert) ~ 1 + perf + perf² + Alter (stückweise) + Liga-Median(log10 Marktwert) + auslaufend
  mit perf = Rollen-Score/100, Alter = (Alter-25), plus Knicke ab 28 und ab 31 und unter 23;
  auslaufend = zwei Indikatoren (Restlaufzeit < 1 Jahr, 1 bis < 2 Jahre).
Je Rollengruppe (= Kandidatenpool der Rolle) ein OLS-Fit über Spieler mit Mindestminuten.

Restlaufzeit nur als Indikator, NICHT linear: lange Verträge sind eine Folge hoher Marktwerte (umgekehrte
Kausalität). Die lineare Variante hatte +0,02 CV-R², belohnte aber Spieler mit langem Vertrag und
niedrigem Wert mit absurden Fair Values (x70). Die Indikatoren fangen den echten Effekt ab (+0,07 R²):
FM drückt den Wert bei auslaufenden Verträgen. Die Leistung selbst erklärt wenig (+0,02 bis +0,06 R²
über Liga+Alter) - `fair_value` ist daher vor allem "typischer Wert für Liga/Alter/Vertragslage".

Alterskurve: stückweise statt quadratisch. Auf Live-Daten (n ~ 1.000-4.700 je Gruppe, 5-fach CV, 2026-12-05)
ändert das R² kaum (+0,001 bis +0,004; Altersklassen oder Interaktionen auch nicht), bleibt aber gleich
gut und biegt die Kurve bei Älteren nicht künstlich nach oben. Die CV-Streuung liegt bei RMSE ~0,57
(log10) = Faktor ~3,7; deshalb braucht das Moneyball-Flag zusätzlich `fv_z` (Abweichung in Streuungen).

Was das aussagt – und was nicht: `fair_value` ist der FM-Marktwert, den die Regression für diese
Leistung/Alter/Liga/Restlaufzeit erwartet. `fv_ratio = fair_value / value` > 1 heißt: FM bewertet den
Spieler niedriger, als seine Leistung im Pool üblicherweise bewertet wird. Das ist KEIN Beleg für
echten Wert, Entwicklung oder Passung. Die Restlaufzeit steht als Feature drin, weil FM den Wert
bei auslaufenden Verträgen drückt. Die Gütekennzahl (R², n) wird immer mit ausgegeben.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["const", "perf", "perf2", "alter", "ueber28", "ueber31", "unter23", "liga_median", "auslaufend1", "auslaufend2"]
MAX_YEARS = 5.0


def _key(df: pd.DataFrame) -> pd.Series:
    country = df["club_country"].fillna("?") if "club_country" in df else "?"
    return df["league"].fillna("?").astype(str) + "|" + country.astype(str)


def league_medians(players: pd.DataFrame, min_n: int) -> tuple[dict[str, float], float]:
    """-> ({Liga|Land: Median log10(value)} ab min_n Spielern, globaler Median)."""
    v = players[players["value"] > 0]
    logv = np.log10(v["value"].astype(float))
    glob = float(logv.median()) if len(logv) else float("nan")
    grp = logv.groupby(_key(v))
    med = grp.median()[grp.count() >= min_n]
    return med.to_dict(), glob


def remaining_years(df: pd.DataFrame) -> pd.Series:
    end = pd.to_datetime(df["contract_end"], errors="coerce")
    now = pd.to_datetime(df["ingame_date"], errors="coerce")
    return ((end - now).dt.days / 365.25).clip(lower=0.0, upper=MAX_YEARS)


def _indicator(years, cond) -> np.ndarray:
    """0/1-Indikator; NaN bleibt NaN (fehlendes Vertragsende darf nicht als 'nicht auslaufend' gelten)."""
    y = np.asarray(years, dtype=float)
    return np.where(np.isnan(y), np.nan, cond(y).astype(float))


def design(perf, age, league_med, years) -> np.ndarray:
    age = np.asarray(age, dtype=float)
    p = np.asarray(perf, dtype=float) / 100
    n = len(p)
    return np.column_stack(
        [
            np.ones(n),
            p,
            p**2,
            age - 25,
            np.maximum(0, age - 28),
            np.maximum(0, age - 31),
            np.maximum(0, 23 - age),
            np.asarray(league_med, float),
            _indicator(years, lambda y: y < 1),
            _indicator(years, lambda y: (y >= 1) & (y < 2)),
        ]
    )


def add_fair_value(
    df: pd.DataFrame,
    players: pd.DataFrame,
    defaults: dict,
    perf_col: str = "rollen_score",
) -> tuple[pd.DataFrame, dict]:
    """Fügt `fair_value`, `fv_ratio`, `moneyball` hinzu. -> (df, {n, r2, ok, grund}).

    `df` ist der Kandidatenpool der Rolle (schon auf Mindestminuten gefiltert), `players` alle
    Spieler (für die Liga-Mediane). Ohne ausreichend Trainingsdaten bleiben die Spalten NaN."""
    min_n = defaults.get("fv_min_n", 50)
    ratio_min = defaults.get("fv_ratio_min", 2.0)
    out = df.copy()
    out["fair_value"] = np.nan
    out["fv_ratio"] = np.nan
    out["fv_z"] = np.nan
    out["moneyball"] = False

    med, glob = league_medians(players, defaults.get("fv_liga_min_n", 10))
    liga = _key(out).map(med).fillna(glob)
    X = design(out[perf_col], out["age"], liga, remaining_years(out))
    value = out["value"].astype(float)
    complete = np.isfinite(X).all(axis=1) & (value > 0).to_numpy()
    n = int(complete.sum())
    if n < min_n:
        return out, {"n": n, "r2": None, "ok": False, "grund": f"nur {n} Spieler (< {min_n})"}

    y = np.log10(value.to_numpy()[complete])
    beta, *_ = np.linalg.lstsq(X[complete], y, rcond=None)
    resid = y - X[complete] @ beta
    dof = max(len(y) - X.shape[1], 1)
    rmse = float(np.sqrt((resid**2).sum() / dof))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float((resid**2).sum()) / ss_tot if ss_tot > 0 else float("nan")

    ok = np.isfinite(X).all(axis=1)
    fair = np.full(len(out), np.nan)
    fair[ok] = 10 ** (X[ok] @ beta)
    out["fair_value"] = fair
    out["fv_ratio"] = out["fair_value"] / value.where(value > 0)
    # Untergrenze: bei Marktwerten nahe null explodiert das Verhältnis (Rauschen, kein Signal).
    floor = defaults.get("fv_min_fair", 250_000)
    out["fv_z"] = np.log10(out["fv_ratio"]) / rmse  # Abweichung in Modell-Streuungen
    z_min = defaults.get("fv_z_min", 1.5)
    out["moneyball"] = (
        (out["fv_ratio"] >= ratio_min) & (out["fv_z"] >= z_min) & (out["fair_value"] >= floor)
    )
    return out, {
        "n": n,
        "r2": r2,
        "rmse": rmse,
        "ok": True,
        "beta": dict(zip(FEATURES, beta.round(3).tolist())),
    }
