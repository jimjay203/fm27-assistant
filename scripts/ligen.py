"""Liga-Zuordnung: Live-Name (Division im FMMT-Reader) -> Eintrag der Ansehen-Rangliste, Stufe und Gewicht.

Daten: config/ligen.yaml (`ranking` aus der Spiel-Ansicht, `alias` + `alias_regeln` für die Live-Namen,
`stufen_gewichte`). Ligen ohne Alias haben keine Stufe: `stufe()` und `gewicht()` liefern dann None.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

MIT_LAND = re.compile(r"^(.*) \(([^()]+)\)$")


def _minuten(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(v) else v


def mit_land(df):
    """Exporte: 'Liga (Land)' aus league + club_country, damit gleichnamige Ligen eindeutig aufgelöst werden.

    'Bundesliga' heißt die Liga in Deutschland und Österreich; erst das Land des Vereins trennt sie (wie der
    league_ranking-Join in per90.load_wide). Ohne Land bleibt der Name unverändert."""
    if "club_country" not in df or "league" not in df:
        return df.get("league")
    ok = df["league"].notna() & df["club_country"].notna()
    out = df["league"].copy()
    out[ok] = df.loc[ok, "league"].astype(str) + " (" + df.loc[ok, "club_country"].astype(str) + ")"
    return out


class Ligen:
    def __init__(self, cfg: dict):
        self.ranking = {
            (e["liga"], e["land"]): {**e, "rang": i}
            for i, e in enumerate(cfg.get("ranking") or [], 1)
        }
        self.stufen = list(
            dict.fromkeys(e["ansehen"] for e in cfg.get("ranking") or [])
        )  # beste zuerst
        self.alias = {
            str(k).casefold(): (v["liga"], v["land"]) for k, v in (cfg.get("alias") or {}).items()
        }
        self.regeln = [
            (re.compile(r["muster"], re.IGNORECASE), (r["liga"], r["land"]))
            for r in cfg.get("alias_regeln") or []
        ]
        self.gewichte = cfg.get("stufen_gewichte") or {}
        self.standard = cfg.get("gewichtung_standard", "standard")
        self._cache: dict[str, dict | None] = {}

    @classmethod
    def laden(cls, config_dir: Path | None = None) -> Ligen:
        return cls(common.load_yaml("ligen.yaml", config_dir))

    def aufloesen(self, division) -> dict | None:
        """Ranking-Eintrag (liga, land, ansehen, pos, rang) zur Live-Division oder zu 'Liga (Land)', sonst None."""
        if not isinstance(division, str) or not division:
            return None
        if division in self._cache:
            return self._cache[division]
        m = MIT_LAND.match(division)
        key = (m[1], m[2]) if m and (m[1], m[2]) in self.ranking else None
        if key is None:
            key = self.alias.get(division.casefold())
        if key is None:
            key = next((k for rx, k in self.regeln if rx.search(division)), None)
        entry = self.ranking.get(key) if key else None
        self._cache[division] = entry
        return entry

    def stufe(self, division) -> str | None:
        e = self.aufloesen(division)
        return e["ansehen"] if e else None

    def gewicht(self, division, schema: str | None = None) -> float | None:
        """Faktor der Stufe im gewählten Schema (None = keine Stufe bekannt)."""
        st = self.stufe(division)
        if st is None:
            return None
        return (self.gewichte.get(schema or self.standard) or {}).get(st)

    def gewicht_saisons(self, league, schema=None, league_vs=None, min_neu=None, min_vs_w=None):
        """Liga-Gewicht je Saison (Saisonbasis, per90.kombinieren): Mittel der Gewichte der Liga der laufenden
        Saison und der Vorsaison, gewichtet mit den Minuten (Vorsaison x w). Ohne Vorsaison = gewicht()."""
        g = self.gewicht(league, schema)
        mv = _minuten(min_vs_w)
        if mv <= 0:
            return g
        teile = [(x, m) for x, m in ((g, _minuten(min_neu)), (self.gewicht(league_vs, schema), mv))
                 if x is not None and m > 0]  # fmt: skip
        if not teile:
            return g
        return sum(x * m for x, m in teile) / sum(m for _, m in teile)

    def gewicht_spalte(self, df, schema=None):
        """gewicht_saisons() je Zeile eines DataFrames (ohne Saisonspalten: gewicht() der Liga)."""
        if "min_vs_w" not in df or "league_vs" not in df:
            return df["league"].map(lambda d: self.gewicht(d, schema))
        werte = [
            self.gewicht_saisons(lg, schema, lv, mn, mv)
            for lg, lv, mn, mv in zip(df["league"], df["league_vs"], df["min_neu"], df["min_vs_w"], strict=True)
        ]  # fmt: skip
        return pd.Series([np.nan if x is None else x for x in werte], index=df.index, dtype=float)

    def schemata(self) -> list[str]:
        return list(self.gewichte)

    def stufe_index(self, stufe: str) -> int:
        """0 = beste Stufe. Wirft ValueError bei unbekannter Stufe."""
        return self.stufen.index(stufe)
