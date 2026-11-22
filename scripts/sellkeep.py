"""Sell/Keep-Vorschlag für den eigenen Kader (Kaskade nach FMMT-27, Schwellen: rollen.yaml sell_keep).

Reihenfolge der Regeln (die erste, die greift, entscheidet):
  1. Zu wenig Minuten: jung (<= `jung`) -> Entwickeln / Leihe prüfen / Abgeben prüfen nach
     Ability-vs-Alter (exakte Attribute nötig); älter -> Zu wenig Daten
  2. Vertrag läuft <= `vertrag_monate` aus: Stammspieler/Ersatz -> Verlängern prüfen, sonst Jetzt verkaufen
  3. Marktwert >= `teuer_faktor` * Fair Value und (kein Stammspieler oder Alter >= Peak-1) -> Teuer verkaufen
  4. Anteil Minuten < `ersatz_anteil` -> Überzählig
  5. Alter >= Peak und kein Stammspieler -> Vor Abfall verkaufen
  6. sonst Behalten
Stammspieler = Minuten / Minuten des meistgenutzten Kaderspielers >= `stamm_anteil`.

Das ist ein Vorschlag, keine Entscheidung. Entscheidungen mit Messkriterium + Prüftermin in log.md.
Eigene Spieler: Snapshot-Typ `live` (player_info.eigen) oder --verein "<Name>" bei Exporten.

Aufruf:  uv run python scripts/sellkeep.py --save werder [--verein "Werder Bremen"]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import per90
import value

GROUP_BY_POS = {
    "ST": "gruppe_st",
    "AM": "gruppe_am",
    "M": "gruppe_mid",
    "DM": "gruppe_mid",
    "D": "gruppe_def",
    "WB": "gruppe_def",
    "GK": "gruppe_gk",
}
MIN_ATTR_COVER = 0.8  # Anteil des Archetyp-Gewichts, der als exaktes Attribut vorliegen muss


def pos_tokens(pos) -> list[str]:
    if not isinstance(pos, str):
        return []
    tokens = [t.strip().split()[0].upper() for t in pos.replace("/", ",").split(",") if t.strip()]
    return [per90.POS_ALIAS.get(t, t) for t in tokens]  # deutsche Export-Kürzel normalisieren


def ability_score(attrs: dict[str, float], weights: dict[str, float]) -> float:
    """Gewichtetes Mittel der exakten Attribute (1-20); NaN bei zu geringer Abdeckung."""
    have = {a: w for a, w in weights.items() if pd.notna(attrs.get(a))}
    if sum(have.values()) < MIN_ATTR_COVER * sum(weights.values()):
        return float("nan")
    return sum(attrs[a] * w for a, w in have.items()) / sum(have.values())


def best_ability(pos, attrs: dict[str, float], cfg: dict) -> float:
    ab = cfg["ability"]
    names = {n for t in pos_tokens(pos) for n in ab["position"].get(t, [])}
    scores = [ability_score(attrs, ab["archetypen"][n]) for n in names]
    scores = [s for s in scores if pd.notna(s)]
    return max(scores) if scores else float("nan")


def vs_alter(ability: float, age, cfg: dict) -> float:
    """Ability in % des Benchmarks für das Alter (15..24 geklemmt); NaN ohne Ability/Alter."""
    if pd.isna(ability) or pd.isna(age):
        return float("nan")
    bench = cfg["ability"]["alter_benchmark"]
    return round(ability / bench[min(max(int(age), 15), 24)] * 100)


def classify(p: dict, sk: dict) -> tuple[str, str]:
    """p: age, minutes, share, contract_end, ingame_date, vs_alter, value, fair_value, pos."""
    age = p.get("age")
    minutes = 0 if pd.isna(p.get("minutes")) else p["minutes"]
    share = 0.0 if pd.isna(p.get("share")) else p["share"]
    peak = sk["peak_alter"]["GK" if "GK" in pos_tokens(p.get("pos")) else "default"]
    starter = share >= sk["stamm_anteil"]
    backup = share >= sk["ersatz_anteil"]

    if minutes < sk["min_minuten"]:
        if pd.notna(age) and age <= sk["jung"]:
            va = p.get("vs_alter")
            if pd.isna(va):
                return "Zu wenig Daten", f"{int(minutes)} Min., keine exakten Attribute"
            if va >= sk["vs_alter_entwickeln"]:
                return "Entwickeln", f"{va:.0f} % des Alters-Benchmarks"
            if va >= sk["vs_alter_leihe"]:
                return "Leihe prüfen", f"{va:.0f} % des Alters-Benchmarks"
            return "Abgeben prüfen", f"{va:.0f} % des Alters-Benchmarks"
        return "Zu wenig Daten", f"{int(minutes)} Min. (< {sk['min_minuten']})"

    end = pd.to_datetime(p.get("contract_end"), errors="coerce")
    today = pd.to_datetime(p.get("ingame_date"), errors="coerce")
    if pd.notna(end) and pd.notna(today):
        months = (end - today).days / 30.44
        if months <= sk["vertrag_monate"]:
            label = "Verlängern prüfen" if backup else "Jetzt verkaufen"
            return label, f"Vertrag noch {max(months, 0):.0f} Mon."

    v, fair = p.get("value"), p.get("fair_value")
    expensive = pd.notna(v) and pd.notna(fair) and fair > 0 and v >= sk["teuer_faktor"] * fair
    if expensive and (not starter or (pd.notna(age) and age >= peak - 1)):
        return "Teuer verkaufen", f"Marktwert {v / fair:.1f}x Fair Value"
    if not backup:
        return "Überzählig", f"{share:.0%} der Top-Minuten"
    if pd.notna(age) and age >= peak and not starter:
        return "Vor Abfall verkaufen", f"Alter {int(age)} >= {peak}, {share:.0%} der Top-Minuten"
    return "Behalten", f"{share:.0%} der Top-Minuten"


def squad_status(players: pd.DataFrame, conn, verein: str | None) -> pd.Series:
    """kader | leihe_ein | leihe_aus je Spieler (sonst NaN): live-Flag, sonst über --verein."""
    info = pd.read_sql_query(
        "SELECT snapshot_id, player_uid, field, text FROM player_info "
        "WHERE field IN ('eigen', 'ausgeliehen_von')",
        conn,
    )
    keys = pd.MultiIndex.from_frame(players[["snapshot_id", "player_uid"]])

    def field(name: str) -> pd.Series:
        f = info[info["field"] == name].set_index(["snapshot_id", "player_uid"])["text"]
        return pd.Series(f.reindex(keys).to_numpy(), index=players.index)

    status = field("eigen")
    if verein:
        owner = field("ausgeliehen_von")
        at_club = players["club"] == verein
        by_name = np.select(
            [at_club & (owner.isna() | (owner == verein)), at_club, owner == verein],
            ["kader", "leihe_ein", "leihe_aus"],
            default="",
        )
        status = status.where(status.notna(), pd.Series(by_name, index=players.index))
        status = status.replace("", np.nan)
    return status


def group_scores(players, attrs, cfg) -> pd.DataFrame:
    """rollen_score/fair_value je Spieler aus seiner Hauptgruppe (erster Positions-Token)."""
    cols = ["player_uid", "rollen_score", "fair_value", "fv_ratio"]
    frames = []
    for role in sorted(set(GROUP_BY_POS.values())):
        try:
            df = value.candidates(players, attrs, cfg, role)
        except SystemExit:  # KPIs fehlen in den Daten: Gruppe überspringen, Meldung kam schon
            continue
        main_group = df["position"].map(lambda p: GROUP_BY_POS.get((pos_tokens(p) or [""])[0]))
        frames.append(df.loc[main_group == role, cols])
    return pd.concat(frames).drop_duplicates("player_uid") if frames else pd.DataFrame(columns=cols)


def build(players, attrs, cfg, status: pd.Series) -> pd.DataFrame:
    sk = cfg["sell_keep"]
    own = players[status.notna()].copy()
    own["status"] = status[own.index]
    own = own.merge(group_scores(players, attrs, cfg), on="player_uid", how="left")
    acols = [c for c in attrs.columns if c.startswith("attr_")]
    own = own.merge(
        attrs[["snapshot_id", "player_uid", *acols]], on=["snapshot_id", "player_uid"], how="left"
    )
    top = own.loc[own["status"] == "kader", "minutes"].max()
    own["share"] = own["minutes"].astype(float) / top if pd.notna(top) and top > 0 else np.nan
    own["ability"] = [
        best_ability(r["position"], {c[5:]: r[c] for c in acols}, cfg) for _, r in own.iterrows()
    ]
    own["vs_alter"] = [vs_alter(r["ability"], r["age"], cfg) for _, r in own.iterrows()]
    labels = []
    for _, r in own.iterrows():
        if r["status"] == "kader":
            labels.append(classify({**r.to_dict(), "pos": r["position"]}, sk))
        elif r["status"] == "leihe_ein":
            wert = f"Marktwert {r['value'] / 1e6:.1f} Mio." if pd.notna(r["value"]) else "kein Wert"
            labels.append(("Leihe (Kaufentscheid)", wert))
        else:
            labels.append(("Verliehen", "Rückkehr/Verlauf prüfen"))
    own["vorschlag"] = [lb for lb, _ in labels]
    own["grund"] = [g for _, g in labels]
    return own


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--verein", help="Eigener Verein (nur für Exporte nötig; live setzt das selbst)"
    )
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args(argv)

    save = common.resolve_save(a.save)
    conn = common.connect(a.db)
    players, attrs = per90.load_wide(conn, save)
    if players.empty:
        common.die(f"Keine Spielerdaten für Save '{save}' – erst live.py/import.py ausführen.")
    cfg = common.load_yaml("rollen.yaml", a.config_dir)
    status = squad_status(players, conn, a.verein)
    if status.notna().sum() == 0:
        common.die(
            'Keine eigenen Spieler erkannt: live-Snapshot fehlt oder --verein "<Name>" setzen.'
        )
    own = build(players, attrs, cfg, status)
    own["wert_mio"] = own["value"] / 1e6
    cols = ["name", "position", "age", "minutes", "share", "status", "wert_mio", "fv_ratio",
            "vs_alter", "contract_end", "vorschlag", "grund"]  # fmt: skip
    table = own[cols].sort_values(["status", "vorschlag", "name"]).round(2)
    if a.csv:
        table.to_csv(a.csv, index=False)
        print(f"{len(table)} Zeilen -> {a.csv}")
        return
    from tabulate import tabulate

    print(tabulate(table, headers="keys", tablefmt="github", showindex=False))
    print(
        "\nVorschlag, keine Entscheidung. Schwellen: rollen.yaml sell_keep (Setzungen aus FMMT-27, "
        "ungeprüft). Fair Value fehlt, wenn die Gruppe < fv_min_n Spieler hat."
    )


if __name__ == "__main__":
    main()
