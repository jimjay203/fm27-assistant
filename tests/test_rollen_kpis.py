"""config/rollen_kpis.yaml: Konsistenz von Bausteinen, Rollen, Statistiknamen und Quellen."""

import common

CFG = common.load_yaml("rollen_kpis.yaml")
ROLLEN = CFG["rollen"]
BAUSTEINE = CFG["bausteine"]

# Die 68 Rollen der Quelle (wissen/rollen.md), je Positionsgruppe der Quelle.
QUELLE = {
    "Torwart": ["Torwart", "Linientorhüter", "Libero-Torhüter", "Kompromissloser Torhüter", "Ballspielender Torhüter"],
    "Innenverteidigung": [
        "Innenverteidiger", "Stoppender Innenverteidiger", "Absichernder Innenverteidiger",
        "Ballspielender Innenverteidiger", "Kompromissloser Innenverteidiger", "Aufrückender Innenverteidiger",
        "Halbraumverteidiger", "Stoppender Halbraumverteidiger", "Absichernder Halbraumverteidiger",
        "Hinterlaufender Halbraumverteidiger",
    ],
    "Außen-/Flügelverteidiger": [
        "Außenverteidiger", "Flügelverteidiger", "Abwartender Außenverteidiger", "Pressender Außenverteidiger",
        "Inverser Außenverteidiger", "Abwartender Flügelverteidiger", "Pressender Flügelverteidiger",
        "Inverser Flügelverteidiger", "Spielmachender Flügelverteidiger", "Vorgeschobener Flügelverteidiger",
    ],
    "Defensives Mittelfeld": [
        "Defensiver Mittelfeldspieler", "Halbverteidiger", "Abschirmender Sechser", "Pressender Sechser",
        "Flügelsichernder Sechser", "Tiefer Spielmacher", "Abkippender Sechser", "Box-to-Box-Spieler",
        "Box-to-Box-Spielmacher",
    ],
    "Zentrales Mittelfeld": [
        "Zentraler Mittelfeldspieler", "Abschirmender Achter", "Pressender Achter", "Flügelsichernder Achter",
        "Spielmacher", "Weiter Achter", "Vorgeschobener Spielmacher",
    ],
    "Offensives Mittelfeld": [
        "Offensiver Mittelfeldspieler", "Mitarbeitender Zehner", "Zentraler Umschaltzehner",
        "Ausweichender Umschaltzehner", "Freigeist", "Halbraumspieler", "Zweiter Stürmer",
    ],
    "Flügel": [
        "Äußerer Mittelfeldspieler", "Flügelspieler", "Mitarbeitender Außenspieler", "Mitarbeitender Flügelspieler",
        "Äußerer Umschaltspieler", "Umschaltflügelspieler", "Inverser Umschaltflügelspieler", "Halbraumflügel",
        "Äußerer Spielmacher", "Inverser Außenstürmer", "Außenstürmer",
    ],
    "Stürmer": [
        "Mittelstürmer", "Mitarbeitender Mittelstürmer", "Zentraler Umschaltstürmer", "Ausweichender Umschaltstürmer",
        "Hängende Spitze", "Falsche Neun", "Zielspieler", "Knipser", "Halbraumstürmer",
    ],
}  # fmt: skip
ALLE = [r for rs in QUELLE.values() for r in rs]


def known_stats() -> set[str]:
    spalten = common.load_yaml("spalten.yaml")
    live = common.load_yaml("live_spalten.yaml")
    known = {(v if isinstance(v, str) else v["name"]) for v in spalten["spalten"].values()}
    known |= set(spalten["abgeleitet"]) | {s["name"] for s in live["stats"].values()}
    known |= {q["name"] for q in live["quoten"]}
    return known


def test_exactly_the_68_source_roles_are_defined():
    assert len(ALLE) == 68 == len(set(ALLE))
    assert set(ROLLEN) == set(ALLE)
    assert not set(ALLE) - set(ROLLEN) and not set(ROLLEN) - set(ALLE)


def test_every_role_has_valid_fields_and_existing_blocks_and_groups():
    for name, r in ROLLEN.items():
        assert r["phase"] in ("mit", "ohne", "std"), name
        assert r["gruppe"] in CFG["positionsgruppen"], name
        assert r["verlaesslichkeit"] in ("hoch", "mittel", "gering"), name
        assert r["begruendung"].strip(), name
        assert r["bausteine"], name
        for b, w in r["bausteine"].items():
            assert b in BAUSTEINE, f"{name}: Baustein {b}"
            assert isinstance(w, int) and 1 <= w <= 4, f"{name}: Gewicht {b}={w}"
        if r["verlaesslichkeit"] == "gering":
            assert r.get("luecken"), f"{name}: 'gering' braucht eine Begründung unter luecken"


def test_blocks_use_known_stats_and_valid_options():
    known = known_stats()
    for key, b in BAUSTEINE.items():
        assert b["stats"], key
        for s in b["stats"]:
            assert s["stat"] in known, f"{key}: Statistik {s['stat']} ist nicht gemappt"
            assert s["art"] in ("p90", "pct", "direkt"), key
            assert s.get("richtung", "hoch") in ("hoch", "niedrig"), key
    used = {b for r in ROLLEN.values() for b in r["bausteine"]}
    assert used == set(BAUSTEINE), f"ungenutzte Bausteine: {set(BAUSTEINE) - used}"


def test_wie_roles_point_to_an_existing_role_with_same_blocks():
    for name, r in ROLLEN.items():
        if "wie" in r:
            assert r["wie"] in ROLLEN, name
            assert r["bausteine"] == ROLLEN[r["wie"]]["bausteine"], (
                f"{name} weicht von {r['wie']} ab"
            )
    assert (
        sum("wie" in r for r in ROLLEN.values()) >= 6
    )  # laut Quelle mindestens sechs textgleiche Rollen


def test_position_groups_use_valid_rules():
    for g, rules in CFG["positionsgruppen"].items():
        for rule in rules:
            assert rule["pos"] in {"GK", "D", "WB", "DM", "M", "AM", "ST"}, g
            assert set(rule.get("seiten", [])) <= {"R", "L", "C"}, g


def test_phase_counts_match_the_source_exactly():
    """Quelle (Zweierkette): 11 Standardrollen, 28 Rollen ohne Ball (Defensive), 29 mit Ball (Offensive)."""
    phases = [r["phase"] for r in ROLLEN.values()]
    assert {p: phases.count(p) for p in ("mit", "ohne", "std")} == {
        "mit": 29,
        "ohne": 28,
        "std": 11,
    }
