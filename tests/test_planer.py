"""Kaderplaner: Formationen-Konsistenz, Rollenoptionen, Slot-Bewertung, Aufstellung, DB-Adapter."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import benchmark as b
import common
import ligen
import numpy as np
import pandas as pd
import planer
import pytest
import rollen
from conftest import mini_rk

RK = common.load_yaml("rollen_kpis.yaml")
FORM = common.load_yaml("formationen.yaml")
SLOTS = common.load_yaml("taktik_slots.yaml")["slots"]
POS = common.load_yaml("rollen_positionen.yaml")["positionen"]
FIX = Path(__file__).parent / "fixtures" / "echt"


# ------------------------------------------------------------------ Konfiguration


def test_formationen_sind_vollstaendig_und_passen_zu_den_positionen():
    assert FORM["standard"] in FORM["formationen"]
    for name, f in FORM["formationen"].items():
        slots = f["slots"]
        assert len(slots) == 11, name
        assert sum(s["position"] == "TW" for s in slots.values()) == 1, name
        for sn, s in slots.items():
            assert s["position"] in POS, (name, sn)
            opt = planer.slot_optionen(RK, POS, s)
            assert opt["mit"] and opt["ohne"], (name, sn)
            assert 0 <= s["x"] <= 100 and 0 <= s["y"] <= 100


def test_rollen_je_position_existieren_und_passen_zur_phase():
    for pos, e in POS.items():
        assert e.get("quelle"), pos
        for phase in ("mit", "ohne"):
            assert len(e[phase]) == len(set(e[phase])), (pos, phase)
            for n in e[phase]:
                r = RK["rollen"].get(rollen.aufloesen(n, RK))
                assert r, (pos, n)
                assert r["phase"] in (phase, "std"), (pos, phase, n)


def test_zm_hat_die_rollen_aus_fm27():
    # Screenshot FM27, M (Z), mit Ball (Jimmy, 2026-11-22)
    zm = POS["ZM"]["mit"]
    for n in ("Offensiver Mittelfeldspieler", "Vorgeschobener Spielmacher", "Weiter Achter",
              "Halbraumspieler", "Spielmacher"):  # fmt: skip
        assert n in zm


def test_vorbelegung_4231_kommt_aus_taktik_slots():
    ctx = SimpleNamespace(rk=RK, formationen=FORM, slots_taktik=SLOTS, positionen=POS)
    meta = planer.formationen_meta(ctx)
    slots = meta["4-2-3-1"]["slots"]
    assert set(slots) == set(SLOTS)
    for sn, s in SLOTS.items():
        assert (slots[sn]["mit"], slots[sn]["ohne"]) == (s["mit"], s["ohne"]), sn
    # andere Formationen: erste Standardrolle (phase std) der Position
    assert meta["4-3-3"]["slots"]["ST"]["mit"] == "Mittelstürmer"
    assert meta["4-3-3"]["slots"]["ZM r"]["mit"] == "Zentraler Mittelfeldspieler"


def test_unbekannte_position_wird_gemeldet():
    with pytest.raises(SystemExit, match="fehlt in config/rollen_positionen.yaml"):
        planer.slot_optionen(RK, POS, {"position": "XY"})


def test_rollenoptionen_nach_phase_und_mit_aliasnamen():
    opt = planer.rollen_optionen(mini_rk(), ["st"])
    assert opt == {"mit": ["Mit", "Neuer Name"], "ohne": ["Ohne"]}
    iv = planer.rollen_optionen(RK, ["iv"])
    assert "Spielaufbauender Innenverteidiger" in iv["mit"]
    assert "Spielaufbauender Innenverteidiger" not in iv["ohne"]
    assert "Innenverteidiger" in iv["mit"] and "Innenverteidiger" in iv["ohne"]  # std: beide Phasen


# ------------------------------------------------------------------ Bewertung


def test_plan_setzt_niemanden_doppelt_und_zeigt_nur_echte_verbesserungen(mini_ctx):
    p = planer.plan(mini_ctx, "2er", {}, planer.Filter())
    elf = p["elf"]
    assert sorted(elf.values()) == ["A", "B"]  # C hat zu wenige Minuten; A und B je einmal
    for s in p["slots"].values():
        basis = s["basis"]
        assert basis is not None
        assert s["verbesserungen"], "es gibt bessere Kandidaten"
        assert all(z["paar_gew"] > basis and z["delta"] > 0 for z in s["verbesserungen"])
        deltas = [z["delta"] for z in s["verbesserungen"]]
        assert deltas == sorted(deltas, reverse=True)
        assert len(s["verbesserungen"]) <= planer.Filter().top_kandidaten
        assert {o["uid"] for o in s["ohne_wertung"]} == {"C"}
        assert "Min." in s["ohne_wertung"][0]["grund"]
    # Slot mit B (schwächer) hat mehr Verbesserungen als der Slot mit A
    nach_uid = {elf[sn]: s["n_verbesserungen"] for sn, s in p["slots"].items()}
    assert nach_uid["B"] > nach_uid["A"]


def test_filter_alter_und_marktwert_greifen(mini_ctx):
    f = planer.Filter(max_alter=25, max_wert_mio=30, top_kandidaten=1000)
    p = planer.plan(mini_ctx, "2er", {}, f)
    zeilen = [z for s in p["slots"].values() for z in s["verbesserungen"]]
    assert zeilen
    assert all(z["age"] <= 25 and z["value"] <= 30e6 for z in zeilen)


def test_baustein_detail_und_aliasrolle(mini_ctx):
    p = planer.plan(
        mini_ctx, "2er", {"ST r": {"mit": "Neuer Name", "ohne": "Ohne"}}, planer.Filter()
    )
    s = p["slots"]["ST r"]
    assert s["gewertet_als"]["mit"] == "Mit"
    z = s["eigene"][0]
    assert set(z["bausteine"]["mit"]) == {"tore"} and set(z["bausteine"]["ohne"]) == {"fouls"}


def test_unpassende_rolle_und_formation_werden_abgelehnt(mini_ctx):
    with pytest.raises(SystemExit, match="passt nicht"):
        planer.plan(mini_ctx, "2er", {"ST r": {"mit": "Ohne"}}, planer.Filter())
    with pytest.raises(SystemExit, match="Formation"):
        planer.plan(mini_ctx, "9-9-9", {}, planer.Filter())
    with pytest.raises(SystemExit, match="Liga-Stufe"):
        planer.plan(mini_ctx, "2er", {}, planer.Filter(min_stufe="Weltklasse"))


def test_luecken_benennen_fehlende_statistik(mini_ctx):
    df = mini_ctx.df.drop(columns=["f"])
    ctx = planer.kontext_bauen(
        df, mini_ctx.rk, mini_ctx.lg, {"min_minuten": 900}, mini_ctx.formationen
    )
    assert ctx.luecken["st"]["statistiken"] == {"f": "fehlt in den Daten"}
    lu = planer.slot_luecken(ctx, "Mit", "Ohne")
    assert {"phase": "ohne", "rolle": "Ohne", "baustein": "fouls", "entfaellt": True,
            "statistiken": {"f": "fehlt in den Daten"}} in lu  # fmt: skip
    # ohne Baustein keine Wertung ohne Ball -> kein Paar-Score -> niemand bewertbar
    p = planer.plan(ctx, "2er", {}, planer.Filter())
    assert all(s["gesetzt"] is None for s in p["slots"].values())
    # leere Kandidatenmenge + Ligafilter: kein Absturz (Regression rollen.kandidaten_slot)
    p = planer.plan(ctx, "2er", {}, planer.Filter(min_stufe="Gut"))
    assert all(s["n_kandidaten"] == 0 for s in p["slots"].values())


def test_aufstellung_ueberspringt_verliehene():
    eigene = {
        "S1": pd.DataFrame({"uid": ["X", "Y"], "paar_gew": [90.0, 50.0], "eigen": ["leihe_aus", "kader"]}),
        "S2": pd.DataFrame({"uid": ["Y"], "paar_gew": [60.0], "eigen": ["kader"]}),
    }  # fmt: skip
    assert planer.aufstellung(eigene) == {"S1": None, "S2": "Y"}


# ------------------------------------------------------------------ Datenbasis und DB-Adapter


def test_datenbasis_wie_bisher_im_reader():
    assert b.datenbasis("ST (Z)", 900, {"distanz_km": 100.0, "sprints_p90": 20}) == "voll"
    assert b.datenbasis("ST (Z)", 900, {"distanz_km": 50.0, "sprints_p90": 20}) == "reduziert"
    assert b.datenbasis("ST (Z)", 900, {"distanz_km": 100.0}) == "reduziert"
    assert b.datenbasis("ST (Z)", 0, {"distanz_km": 100.0, "sprints_p90": 1}) == "reduziert"
    assert b.datenbasis("ST (Z)", 900, {"distanz_km": np.nan, "sprints_p90": 1}) == "reduziert"
    assert b.datenbasis("TW", 900, {"par_pct": 70.0}) == "voll"
    assert b.datenbasis("TW", 900, {"par_pct": np.nan, "distanz_km": 100.0}) == "reduziert"


def test_ligen_trennen_gleichnamige_ligen_ueber_das_land():
    lg = ligen.Ligen.laden()
    de, at = lg.stufe("Bundesliga (Deutschland)"), lg.stufe("Bundesliga (Österreich)")
    assert de and at and lg.stufe_index(de) < lg.stufe_index(at)
    assert lg.stufe("Serie A (Italien)") is not None  # Exportname, kein Live-Alias nötig
    assert lg.stufe("Bundesliga") == de  # Live-Name über den Alias wie bisher
    df = pd.DataFrame(
        {"league": ["Bundesliga", "Bundesliga", None], "club_country": ["Österreich", None, "X"]}
    )
    out = ligen.mit_land(df)
    assert out[:2].tolist() == ["Bundesliga (Österreich)", "Bundesliga"] and pd.isna(out[2])


def test_benchmark_load_db_nutzt_liga_mit_land():
    fi, c = _fm_import(), common.connect(":memory:")
    for f in ("2026-10-11_kader.csv", "2026-10-11_suche_stuermer.csv", "2027-01-14_kader.csv"):
        fi.import_file(c, "test", FIX / f, common.load_yaml("spalten.yaml"), warn=lambda m: None)
    df = b.load_db(c, "test")
    # nur der neueste Kader-Snapshot: Füllkrug steht nur im alten Kader
    assert "Niclas Füllkrug" not in set(df["name"]) and "Karl Hein" in set(df["name"])
    assert df.attrs["snapshots"] == {"kader": "2027-01-14", "suche": "2026-10-11"}
    assert df.attrs["date"] == "2027-01-14"
    lg = ligen.Ligen.laden()
    wien = df[df["club"] == "Austria Wien"]
    assert wien["league"].iat[0] == "Bundesliga (Österreich)"
    assert lg.stufe(wien["league"].iat[0]) == lg.stufe("Bundesliga (Österreich)")
    assert df.loc[df["club"].isin(["Bahia", "Botafogo"]), "league"].map(lg.stufe).notna().all()
    assert set(df["datenbasis"]) <= {"voll", "reduziert"}  # nicht mehr "unbekannt"
    erwartet = [b.datenbasis(r.position, r.minutes, r._asdict()) for r in df.itertuples()]
    assert df["datenbasis"].tolist() == erwartet


def _fm_import():
    spec = importlib.util.spec_from_file_location(
        "fm_import", common.ROOT / "scripts" / "import.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_daten_db_nimmt_letzten_kader_und_letzte_suche():
    fi, c = _fm_import(), common.connect(":memory:")
    cfg = common.load_yaml("spalten.yaml")
    for f in ("2026-10-11_kader.csv", "2026-10-11_suche_stuermer.csv", "2027-01-14_kader.csv"):
        fi.import_file(c, "test", FIX / f, cfg, warn=lambda m: None)
    df = planer.daten_db(c, "test")
    assert df.attrs["stand"]["verein"] == "Werder Bremen"
    assert df.attrs["stand"]["kader_datum"] == "2027-01-14"
    eigene = set(df.loc[df["own"], "name"])
    assert "Karl Hein" in eigene
    assert "Niclas Füllkrug" not in set(df["name"])  # nur im alten Kader-Snapshot
    assert df.loc[df["in_suche"], "name"].nunique() == 4
    assert not df.loc[df["in_suche"], "own"].any()
    assert (df["team"] == "Senior Team").all()
    assert set(df["datenbasis"]) <= {"voll", "reduziert"}
    assert "uid" in df
