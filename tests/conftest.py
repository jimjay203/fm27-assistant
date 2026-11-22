"""Gemeinsame Fixtures: synthetischer Kaderplaner-Kontext (eine Gruppe st, zwei Rollen, zwei Slots)."""

import ligen
import numpy as np
import pandas as pd
import planer
import pytest


def mini_rk():
    return {
        "gewichtung_je_gruppe": {"st": "standard"},
        "phasen_gewicht": {"mit": 0.5, "ohne": 0.5},
        "positionsgruppen": {"st": [{"pos": "ST"}]},
        "alias_rollen": {"Neuer Name": "Mit"},
        "bausteine": {
            "tore": {"name": "t", "stats": [{"stat": "x", "art": "pct"}]},
            "fouls": {"name": "f", "stats": [{"stat": "f", "art": "pct", "richtung": "niedrig"}]},
        },
        "rollen": {
            "Mit": {"phase": "mit", "gruppe": "st", "bausteine": {"tore": 1}, "verlaesslichkeit": "mittel"},
            "Ohne": {"phase": "ohne", "gruppe": "st", "bausteine": {"fouls": 1}, "verlaesslichkeit": "mittel"},
        },
    }  # fmt: skip


MINI_FORMATIONEN = {
    "standard": "2er",
    "formationen": {
        "2er": {
            "slots": {
                "ST r": {"gruppen": ["st"], "x": 60, "y": 10},
                "ST l": {"gruppen": ["st"], "x": 40, "y": 10},
            }
        }
    },
}


def mini_df(n=400):
    """n Kandidaten mit gleichmäßig verteilten Werten + drei eigene Spieler (A > B > C)."""
    x = np.linspace(0, 100, n)
    cand = pd.DataFrame(
        {
            "uid": [f"k{i}" for i in range(n)], "name": [f"Kandidat {i}" for i in range(n)],
            "position": "ST (Z)", "minutes": 1500, "team": "Senior Team", "datenbasis": "voll",
            "league": "Bundesliga", "x": x, "f": x[::-1], "club": "B",
            "age": np.where(np.arange(n) % 2 == 0, 22, 31), "value": np.linspace(1e6, 50e6, n),
            "own": False, "eigen": None, "in_suche": True,
        }
    )  # fmt: skip
    own = pd.DataFrame(
        {
            "uid": ["A", "B", "C"], "name": ["Eigen A", "Eigen B", "Eigen C"], "position": "ST (Z)",
            "minutes": [1500, 1500, 100], "team": "Senior Team", "datenbasis": "voll",
            "league": "Bundesliga", "x": [70.0, 50.0, 90.0], "f": [30.0, 50.0, 10.0], "club": "Wir",
            "age": 25, "value": 5e6, "own": True, "eigen": "kader", "in_suche": False,
        }
    )  # fmt: skip
    return pd.concat([cand, own], ignore_index=True)


@pytest.fixture
def mini_ctx():
    return planer.kontext_bauen(
        mini_df(), mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900}, MINI_FORMATIONEN
    )
