"""Spielerprofil: Scores wie im Plan, Aufschlüsselung, Statistiken mit Perzentil, Attribute aus der DB."""

import importlib.util
from pathlib import Path

import common
import planer
import pytest
import spielerprofil as sp

FIX = Path(__file__).parent / "fixtures" / "echt"


def test_profil_scores_stimmen_mit_dem_plan_ueberein(mini_ctx):
    p = planer.plan(mini_ctx, "2er", {}, planer.Filter())
    s = p["slots"]["ST r"]
    k = s["verbesserungen"][0]
    pr = sp.profil(mini_ctx, k["uid"], s["mit"], s["ohne"], vergleich=s["gesetzt"])
    z, v = pr["spieler"], pr["vergleich"]
    assert z["paar_gew"] == pytest.approx(k["paar_gew"], abs=0.01)
    assert v["uid"] == s["gesetzt"] and v["paar_gew"] == pytest.approx(s["basis"], abs=0.01)
    mit = next(r for r in pr["rollen"] if r["phase"] == "mit")
    assert mit["score"][0] == pytest.approx(k["mit"], abs=0.01)
    st = mit["bausteine"][0]["stats"][0]
    assert st["stat"] == "x" and len(st["wert"]) == 2  # Spieler + Vergleich
    assert {"schlecht", "ok", "gut", "score", "vs_top"} <= set(st)


def test_profil_statistiken_mit_perzentil_und_ohne_db(mini_ctx):
    pr = sp.profil(mini_ctx, "A", "Mit", "Ohne")
    assert pr["vergleich"] is None
    weitere = next(g for g in pr["statistiken"] if g["gruppe"] == "Weitere")
    x = next(s for s in weitere["stats"] if s["stat"] == "x")
    assert x["gesamt"] == 70 and x["pro90"] is not None  # Zählwert -> pro 90
    assert (
        0 <= x["perzentil"] <= 100 and x["n_pool"] == 402
    )  # 400 Kandidaten + A + B (C unter 900 Min.)
    assert pr["attribute"]["gruppen"] == [] and "Datenbank" in pr["attribute"]["grund"]


def test_profil_unbekannter_spieler(mini_ctx):
    with pytest.raises(SystemExit, match="nicht in den geladenen Daten"):
        sp.profil(mini_ctx, "gibtsnicht", "Mit", "Ohne")


def test_niedrig_besser_wird_gespiegelt(mini_ctx):
    import pandas as pd

    df = mini_ctx.df.copy()
    df["fouls"] = df["f"]  # A hat wenig Fouls (30) -> hohes Perzentil
    ctx = planer.kontext_bauen(
        df, mini_ctx.rk, mini_ctx.lg, mini_ctx.defaults, mini_ctx.formationen
    )
    pr = sp.profil(ctx, "A", "Mit", "Ohne")
    fouls = next(s for g in pr["statistiken"] for s in g["stats"] if s["stat"] == "fouls")
    assert fouls["niedrig"] and fouls["perzentil"] > 50
    assert isinstance(df, pd.DataFrame)


def _fm_import():
    spec = importlib.util.spec_from_file_location(
        "fm_import", common.ROOT / "scripts" / "import.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_attribute_aus_der_db_exakt_und_als_spanne(tmp_path):
    db = tmp_path / "t.sqlite"
    fi, c = _fm_import(), common.connect(db)
    for f in ("2026-10-11_suche_stuermer.csv", "2027-01-14_kader.csv"):
        fi.import_file(c, "test", FIX / f, common.load_yaml("spalten.yaml"), warn=lambda m: None)
    c.close()
    ctx = planer.kontext_laden("test", db_path=db)
    for uid in ctx.df["uid"]:
        a = sp.attribute_und_info(ctx, ctx.df[ctx.df["uid"] == uid])
        if a["gruppen"]:
            break
    assert a["quelle"]["datum"] in ("2026-10-11", "2027-01-14")
    werte = [x for g in a["gruppen"] for x in g["attribute"]]
    assert werte and all(
        x["wert"] is not None or x["lo"] is not None or x["verdeckt"] for x in werte
    )
    assert a["n_exakt"] + a["n_spanne"] <= len(werte)
    namen = {g["gruppe"] for g in a["gruppen"]}
    assert "Mental" in namen
    hein = ctx.df[ctx.df["name"] == "Karl Hein"]
    tw = sp.attribute_und_info(ctx, hein)
    assert tw["gruppen"] and "Torwart" in {g["gruppe"] for g in tw["gruppen"]}
    assert any(i["feld"] == "groesse" for i in tw["info"])
