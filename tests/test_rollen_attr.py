"""Rollenbasierter Attribut-Filter (rollen_attr.py) und Vergleichspool der OM-Rollen (rollen_kpis.yaml)."""

import benchmark as b
import common
import ligen
import pandas as pd
import pytest
import rollen_attr
import spielerprofil

RA = common.load_yaml("rollen_attribute.yaml")
RK = common.load_yaml("rollen_kpis.yaml")
SLOTS = common.load_yaml("taktik_slots.yaml")["slots"]
LG = ligen.Ligen.laden()

MIT = {"key": ["Passen", "Technik", "Teamwork"], "preferred": ["Dribbling", "Flanken"]}
OHNE = {"key": ["Deckung", "Teamwork"]}


# --------------------------------------------------------------------------- Schwelle und Rollen-Lookup


def test_threshold_follows_target_club_tier_with_default_below():
    assert rollen_attr.schwelle_fuer_stufe("Herausragend", RA) == 12
    assert rollen_attr.schwelle_fuer_stufe("Exzellent", RA) == 12  # Bundesliga
    assert rollen_attr.schwelle_fuer_stufe("Beeindruckend", RA) == 11
    assert rollen_attr.schwelle_fuer_stufe("Gut", RA) == 10
    assert rollen_attr.schwelle_fuer_stufe("Recht gut", RA) == 9
    assert rollen_attr.schwelle_fuer_stufe("Brauchbar", RA) == 8
    assert rollen_attr.schwelle_fuer_stufe(None, RA) == 8


def test_target_tier_comes_from_own_players_not_from_candidates():
    df = pd.DataFrame(
        {"own": [True, True, False, False, False],
         "league": ["Bundesliga (Deutschland)"] * 2 + ["2. Bundesliga (Deutschland)"] * 3}
    )  # fmt: skip
    assert rollen_attr.ziel_stufe(df, LG) == "Exzellent"
    assert rollen_attr.ziel_stufe(df.assign(own=False), LG) is None


def test_role_lookup_uses_alias_in_both_directions_and_reports_missing_phase():
    rk = {"alias_rollen": {"Neu": "Alt"}}
    ra = {"rollen": {"Neu|mit": {"key": ["A"]}, "Nur|mit": {"key": ["B"]}}}
    assert rollen_attr.rolle_def("Neu", "mit", ra, rk)[0] == "Neu|mit"
    assert (
        rollen_attr.rolle_def("Alt", "mit", ra, rk)[0] == "Neu|mit"
    )  # Quelle führt den FM27-Namen
    assert rollen_attr.rolle_def("Nur", "ohne", ra, rk) is None  # kein Ersatz, nur ausweisen
    # echte Konfiguration: Ballspielender IV (Quelle der KPIs) findet den Spielaufbauenden IV der Attribut-Quelle
    assert rollen_attr.rolle_def("Ballspielender Innenverteidiger", "mit", RA, RK)[0] == (
        "Spielaufbauender Innenverteidiger|mit"
    )
    assert rollen_attr.rolle_def("Mittelstürmer", "ohne", RA, RK) is None


def test_every_tactic_slot_has_attributes_with_ball_and_names_match_the_export():
    for slot, s in SLOTS.items():
        assert rollen_attr.rolle_def(s["mit"], "mit", RA, RK), slot
    bekannt = {a for g in spielerprofil.ATTRIBUT_GRUPPEN.values() for a in g}
    for k, r in RA["rollen"].items():
        for liste in ("key", "preferred", "unnecessary"):
            assert set(r.get(liste) or []) <= bekannt, (k, set(r.get(liste) or []) - bekannt)


# --------------------------------------------------------------------------- Bewertung


def test_span_uses_midpoint_and_safe_requires_lower_bound():
    attrs = {
        "Passen": (None, 10.0, 16.0),  # Mitte 13 -> kein Ausfall, aber lo 10 -> unsicher
        "Technik": (15.0, 15.0, 15.0),  # exakt
        "Teamwork": (None, 8.0, 12.0),  # Mitte 10 -> Ausfall
        "Dribbling": (14.0, 14.0, 14.0),
        "Flanken": (None, None, None),  # verdeckt, ohne Spanne
    }
    r = rollen_attr.bewerten(attrs, MIT, 12)
    assert r["fehlt"] == ["Teamwork"]
    assert r["unsicher"] == ["Passen", "Teamwork"]
    assert r["key_avg"] == pytest.approx((13 + 15 + 10) / 3)
    assert r["pref_avg"] == pytest.approx(14)  # Flanken unbekannt -> nicht im Mittel


def test_pair_counts_shared_key_once_lists_failures_and_unknowns():
    attrs = {
        "Passen": (14.0, 14.0, 14.0), "Technik": (11.0, 11.0, 11.0), "Teamwork": (None, 8.0, 12.0),
        "Deckung": (None, None, None),
    }  # fmt: skip
    p = rollen_attr.paar(attrs, MIT, OHNE, 12)
    assert (p["key_fehlt"], p["key_n"], p["key_unsicher"]) == (
        2,
        3,
        2,
    )  # Teamwork nur einmal, Deckung unbekannt
    assert p["key_mit"] == pytest.approx((14 + 11 + 10) / 3)
    assert p["key_ohne"] == pytest.approx(10)
    assert "Technik 11" in p["ausfaelle"] and "Teamwork 8-12" in p["ausfaelle"]
    assert "unbekannt: Deckung" in p["ausfaelle"]


def test_pair_without_source_entry_for_one_phase_only_rates_the_other():
    attrs = {
        "Passen": (14.0, 14.0, 14.0),
        "Technik": (12.0, 12.0, 12.0),
        "Teamwork": (12.0, 12.0, 12.0),
    }
    p = rollen_attr.paar(attrs, MIT, None, 12)
    assert p["key_ohne"] is None and (p["key_fehlt"], p["key_n"]) == (0, 3)
    leer = rollen_attr.paar(None, MIT, OHNE, 12)
    assert leer["key_fehlt"] is None and "keine Attribute" in leer["ausfaelle"]


def test_most_common_failures_show_rarely_met_keys():
    spieler = [{"Deckung": (7.0, 7.0, 7.0), "Teamwork": (13.0, 13.0, 13.0)}] * 9 + [
        {"Deckung": (13.0, 13.0, 13.0), "Teamwork": (13.0, 13.0, 13.0)}
    ]
    hf = rollen_attr.haeufigste_ausfaelle(spieler, OHNE, 12)
    assert hf[0] == ("Deckung", pytest.approx(90), 10)
    assert rollen_attr.haeufigste_ausfaelle(spieler, None, 12) == []


# --------------------------------------------------------------------------- Laden aus der DB


def test_attribute_loader_prefers_given_snapshot_else_newest_with_attributes():
    conn = common.connect(":memory:")
    for sid, datum in ((1, "2027-01-01"), (2, "2027-05-01"), (3, "2027-06-01")):
        conn.execute(
            "INSERT INTO snapshots VALUES(?, 'w', ?, ?, 'suche', 'x')", (sid, datum, f"f{sid}")
        )
    rows = [
        (1, "p", "Passen", 10, 0, 10, 10),
        (2, "p", "Passen", None, 1, 12, 16),
        (3, "q", "Passen", 9, 0, 9, 9),
        (1, "q", "Passen", 15, 0, 15, 15),
    ]
    conn.executemany("INSERT INTO player_attributes VALUES(?,?,?,?,?,?,?)", rows)
    attrs, datum = rollen_attr.attribute_laden(conn, "w", ["p", "q", "x"], {"q": 1})
    assert attrs["p"]["Passen"][1:] == (12, 16) and datum["p"] == "2027-05-01"  # neuester
    assert attrs["q"]["Passen"][0] == 15 and datum["q"] == "2027-01-01"  # bevorzugter Snapshot
    assert "x" not in attrs
    assert rollen_attr.attribute_laden(conn, "anderer", ["p"]) == ({}, {})


# --------------------------------------------------------------------------- Vergleichspool OM


@pytest.mark.parametrize(
    "pos, drin",
    [
        ("M (Z), OM (RLZ)", True),  # Chuki
        ("M/OM (RZ)", True),  # Skyttä
        ("OM (LZ), ST (Z)", True),  # Bøving
        ("DM, M/OM (Z)", True),  # Svanberg
        ("DM, M (Z)", False),  # reiner Achter/Sechser
        ("V (Z), DM, M (Z)", False),
        ("M (Z)", False),
        ("OM (RL)", False),  # nur Flügel
    ],
)
def test_om_pool_requires_central_attacking_midfield(pos, drin):
    assert b.position_ok(pos, RK["positionsgruppen"]["om"]) is drin


def test_om_fix_leaves_other_groups_untouched():
    zm = RK["positionsgruppen"]["zm"]
    assert b.position_ok("DM, M (Z)", zm) and b.position_ok("M (Z)", zm)
    assert all(r["gruppe"] != "om" for n, r in RK["rollen"].items() if n in {
        s["mit"] for s in SLOTS.values() if s["mit"] != "Vorgeschobener Spielmacher"
    })  # fmt: skip


def test_rollen_table_adds_attribute_columns_without_changing_order():
    import rollen

    conn = common.connect(":memory:")
    conn.execute("INSERT INTO snapshots VALUES(1, 'w', '2027-05-31', 'f', 'suche', 'x')")
    conn.executemany(
        "INSERT INTO player_attributes VALUES(1, ?, ?, ?, 0, ?, ?)",
        [("a", "Passen", 8, 8, 8), ("b", "Passen", 15, 15, 15)],
    )
    ra = {"rollen": {"R|mit": {"key": ["Passen"]}}}
    s = {"mit_anzeige": "R", "ohne_anzeige": "S"}
    sub = pd.DataFrame(
        {"uid": ["a", "b", "c"], "name": ["A", "B", "C"], "club": "X", "liga_stufe": "Gut", "age": 25,
         "minutes": 1000, "mit": 50.0, "ohne": 50.0, "paar": [90.0, 50.0, 10.0], "paar_gew": [90.0, 50.0, 10.0],
         "vs_top": 50.0, "value": 1e6, "contract_end": "2030-06-30", "own": False}
    )  # fmt: skip
    cols, _, d_mit, d_ohne = rollen.attribut_spalten(sub, s, {}, ra, conn, "w", 12)
    assert d_mit[0] == "R|mit" and d_ohne is None
    t = pd.concat([sub, cols], axis=1)
    txt = rollen._tabelle(t)
    assert txt.index("| A ") < txt.index("| B ") < txt.index("| C ")  # Reihenfolge unverändert
    assert "1/1" in txt and "0/1" in txt and list(cols["key_fehlt"].isna()) == [False, False, True]


def test_failure_list_is_structured_like_the_text_column():
    attrs = {
        "Passen": (14.0, 14.0, 14.0), "Technik": (11.0, 11.0, 11.0), "Teamwork": (None, 11.0, 15.0),
        "Deckung": (None, None, None),
    }  # fmt: skip
    liste = rollen_attr.ausfall_liste(attrs, MIT, OHNE, 12)
    assert [(e["attribut"], e["art"], e["anzeige"]) for e in liste] == [
        ("Technik", "fehlt", "11"), ("Teamwork", "unsicher", "11-15"), ("Deckung", "unbekannt", "?"),
    ]  # fmt: skip
    assert liste[1]["phasen"] == ["mit", "ohne"] and liste[1]["mitte"] == 13
    assert not liste[1]["exakt"]
    p = rollen_attr.paar(attrs, MIT, OHNE, 12)
    assert p["key_fehlt"] == sum(e["art"] == "fehlt" for e in liste)
    assert p["key_unsicher"] == sum(e["art"] in ("fehlt", "unsicher") for e in liste)
    assert rollen_attr.ausfall_liste(None, MIT, None, 12)[0]["art"] == "unbekannt"
