"""Liga-Zuordnung (Alias), Stufen und Gewichte aus der produktiven config/ligen.yaml."""

import itertools

import common
import ligen
import pytest

CFG = common.load_yaml("ligen.yaml")
LG = ligen.Ligen(CFG)


def test_every_alias_and_rule_target_exists_in_ranking():
    keys = {(e["liga"], e["land"]) for e in CFG["ranking"]}
    for name, v in CFG["alias"].items():
        assert (v["liga"], v["land"]) in keys, f"Alias '{name}': Ziel fehlt im ranking"
    for r in CFG["alias_regeln"]:
        assert (r["liga"], r["land"]) in keys, f"Regel {r['muster']}: Ziel fehlt im ranking"


def test_alias_names_are_unique_ignoring_case():
    names = [str(k).casefold() for k in CFG["alias"]]
    assert len(names) == len(set(names))


def test_resolves_sponsor_names_and_disambiguates_same_names():
    assert LG.stufe("LaLiga EA Sports") == "Herausragend"
    assert LG.stufe("Premier League") == "Herausragend"
    assert (
        LG.aufloesen("Bundesliga")["land"] == "Deutschland"
        and LG.stufe("Bundesliga") == "Exzellent"
    )
    assert (
        LG.aufloesen("ADMIRAL Bundesliga")["land"] == "Österreich"
        and LG.stufe("ADMIRAL Bundesliga") == "Beeindruckend"
    )
    assert LG.aufloesen("Stoiximan Super League")["land"] == "Griechenland"
    assert LG.aufloesen("Brack Super League")["land"] == "Schweiz"
    assert LG.stufe("Sky Bet Championship") == "Gut"
    assert LG.stufe("2. Bundesliga") == "Gut"


def test_rules_cover_league_families_and_case_is_ignored():
    assert LG.aufloesen("Oberliga Hamburg")["liga"] == "Oberliga"
    assert LG.aufloesen("oberliga westfalen")["land"] == "Deutschland"
    assert LG.aufloesen("Campeonato Brasileiro Série A Betano")["liga"] == "Brasileirão"
    assert LG.aufloesen("Campeonato Brasileiro Série B Superbet")["liga"] == "Brasileirão Série B"
    assert LG.aufloesen("Serie C Sky Wifi Girone B")["liga"] == "Serie C"


def test_unknown_or_missing_league_has_no_tier_and_no_weight():
    for d in ("Amateurliga", "Landesliga Bayern/Staffel Südost", "", None, float("nan")):
        assert LG.stufe(d) is None and LG.gewicht(d) is None


def test_weights_cover_every_tier_and_fall_monotonically():
    assert LG.stufen == [
        "Herausragend",
        "Exzellent",
        "Beeindruckend",
        "Gut",
        "Recht gut",
        "Brauchbar",
        "Durchschnittlich",
    ]
    assert set(LG.schemata()) >= {"standard", "mild", "steil"}
    for schema in LG.schemata():
        w = [LG.gewichte[schema][s] for s in LG.stufen]
        assert all(a > b for a, b in itertools.pairwise(w)), (
            f"{schema}: Gewichte müssen mit der Stufe fallen"
        )
        assert LG.gewichte[schema]["Exzellent"] == 1.0, f"{schema}: Bundesliga-Basis soll 1,00 sein"
    assert LG.gewicht("Bundesliga") == 1.0 and LG.gewicht("Bundesliga", "steil") == 1.0
    assert LG.gewicht("Sky Bet League One", "steil") == pytest.approx(0.70)


def test_stufe_index_orders_tiers():
    assert (
        LG.stufe_index("Herausragend")
        == 0
        < LG.stufe_index("Gut")
        < LG.stufe_index("Durchschnittlich")
    )
    with pytest.raises(ValueError):
        LG.stufe_index("Super")


def test_benchmark_min_stufe_filter_ignores_leagues_without_tier():
    import benchmark
    import pandas as pd

    df = pd.DataFrame({"liga_stufe": ["Herausragend", None, float("nan"), "Gut", "Brauchbar"]})
    limit = LG.stufe_index("Gut")
    keep = df["liga_stufe"].map(lambda x: isinstance(x, str) and LG.stufe_index(x) <= limit)
    assert keep.tolist() == [True, False, False, True, False]
    assert benchmark.ligen.Ligen is ligen.Ligen  # benchmark nutzt dasselbe Modul


def test_every_profile_names_a_valid_weighting_scheme_split_attack_defence():
    profile = common.load_yaml("profile.yaml")["profile"]
    for pid, prof in profile.items():
        assert prof["gewichtung"] in LG.schemata(), f"{pid}: Schema fehlt in ligen.yaml"
    defence = {"torwart", "iv_stopper", "iv_spielaufbau", "aussenverteidiger", "wingback"}
    assert {p for p, v in profile.items() if v["gewichtung"] == "mild"} == defence
    assert all(v["gewichtung"] == "standard" for p, v in profile.items() if p not in defence)


def test_thai_t1_is_ranked_and_aliased():
    assert LG.stufe("BYD Sealion 6 League I") == "Recht gut"
    assert LG.aufloesen("BYD Sealion 6 League I")["land"] == "Thailand"
    assert LG.stufe("BYD Seal 5 League II") == "Brauchbar"  # T2 unverändert
    assert LG.aufloesen("Challenger Pro League")["pos"] == 50
