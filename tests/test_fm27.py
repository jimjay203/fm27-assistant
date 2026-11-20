"""Tests mit synthetischen Fixtures (tests/fixtures/*.csv) und einem echten Export-Ausschnitt
(tests/fixtures/echt/, 3 Zeilen) gegen die produktive config/spalten.yaml."""

import importlib.util
import sqlite3
from pathlib import Path

import common
import fmparse
import pandas as pd
import per90
import pytest
import team
import value

FIX = Path(__file__).parent / "fixtures"
CFG = FIX / "config"

_spec = importlib.util.spec_from_file_location(
    "fm_import", Path(common.ROOT) / "scripts" / "import.py"
)
fm_import = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fm_import)


@pytest.fixture
def conn():
    c = common.connect(":memory:")
    spalten = common.load_yaml("spalten.yaml", CFG)
    quiet = lambda m: None
    for f in sorted(FIX.glob("*.csv")):
        fm_import.import_file(c, "test", f, spalten, sep=";", warn=quiet)
    return c


def count(c, table):
    return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# --- Parser ---------------------------------------------------------------------------------
def test_parse_money():
    assert fmparse.parse_money("€1.5M") == 1_500_000
    assert fmparse.parse_money("€250K p/w") == 250_000
    assert fmparse.parse_money("1,5 Mio.", decimal=",") == 1_500_000
    assert fmparse.parse_money("€1M - €2M") == 1_500_000
    assert fmparse.parse_money("Unverkäuflich") is None


def test_parse_number_and_attribute():
    assert fmparse.parse_number("1,234") == 1234
    assert fmparse.parse_number("1.234", decimal=",") == 1234
    assert fmparse.parse_number("45%") == 45
    assert fmparse.parse_attribute("12-15") == (None, True)
    assert fmparse.parse_attribute("-") == (None, True)
    assert fmparse.parse_attribute("14") == (14.0, False)


def test_parse_date_and_annual():
    assert fmparse.parse_date("30.06.2029") == "2029-06-30"
    assert fmparse.to_annual(10, "woche") == 520


def test_parse_mixed_number_formats():
    assert fmparse.parse_number("2.01") == 2.01
    assert fmparse.parse_number("2,01", decimal=",") == 2.01
    assert fmparse.parse_number("2.01", decimal=",") is None  # nicht still zu 201 werden
    assert fmparse.parse_number("1,5") is None  # kein gültiger Tausender
    assert fmparse.parse_number("24,5km", decimal=",", einheit="km") == 24.5
    assert fmparse.parse_number("24,5", decimal=",", einheit="km") is None
    assert fmparse.parse_apps("6 (2)") == (6, 2)
    assert fmparse.parse_apps("3") == (3, 0)
    assert fmparse.parse_apps("-") is None


def test_parse_money_export_formats():
    assert fmparse.parse_money("2,49Mio. €/J.", decimal=",") == pytest.approx(2_490_000)
    assert fmparse.parse_money("997K €/J.", decimal=",") == 997_000
    assert fmparse.money_period("997K €/J.") == "jahr"
    assert fmparse.money_period("€20K p/w") == "woche"
    assert fmparse.money_period("€1.5M") is None
    assert fmparse.parse_money_range("9Mio. € - 11,5Mio. €", ",") == pytest.approx((9e6, 11.5e6))
    assert fmparse.parse_money_range("425K € - 4,3Mio. €", ",") == pytest.approx((425e3, 4.3e6))
    assert fmparse.parse_money_range("3,7Mio. €", ",") == pytest.approx((3.7e6, 3.7e6))
    assert fmparse.parse_money_range("Steht nicht zum Verkauf", ",") is None


def test_filename_convention():
    assert fm_import.parse_filename(Path("2027-01-15_suche_stuermer.csv")) == (
        "2027-01-15",
        "suche",
    )
    assert fm_import.parse_filename(Path("2027-01-15_team_stats.csv")) == (
        "2027-01-15",
        "team_stats",
    )
    with pytest.raises(ValueError):
        fm_import.parse_filename(Path("kader.csv"))


# --- Import ---------------------------------------------------------------------------------
def test_import_idempotent(conn):
    before = {
        t: count(conn, t)
        for t in ("snapshots", "players", "player_stats", "player_attributes", "team_matches")
    }
    spalten = common.load_yaml("spalten.yaml", CFG)
    for f in sorted(FIX.glob("*.csv")):
        fm_import.import_file(conn, "test", f, spalten, sep=";", warn=lambda m: None)
    assert before == {t: count(conn, t) for t in before}
    assert before["snapshots"] == 3


def test_import_values_and_masking(conn):
    row = conn.execute(
        "SELECT wage, value, contract_end, minutes FROM players WHERE player_uid='U0001'"
    ).fetchone()
    assert row[0] % 52 == 0 and row[1] >= 500_000 and row[2].startswith("20") and row[3] > 0
    masked = conn.execute(
        "SELECT COUNT(*) FROM player_attributes WHERE masked=1 AND value IS NULL"
    ).fetchone()[0]
    assert masked > 0
    assert count(conn, "player_raw") > 0  # unbekannte Spalte fx_extra bleibt erhalten


def test_uid_fallback(conn):
    uid = conn.execute("SELECT player_uid FROM players WHERE name='Test Spieler 40'").fetchone()[0]
    assert uid.startswith("Test Spieler 40|19")


def test_wage_period_required(tmp_path):
    c = common.connect(":memory:")
    cfg = common.load_yaml("spalten.yaml", CFG)
    cfg["gehalt"] = {"periode": None}
    with pytest.raises(SystemExit):
        fm_import.import_file(c, "test", FIX / "2027-01-15_kader_test.csv", cfg, sep=";")


def _import_echt(cfg=None):
    c = common.connect(":memory:")
    warnings: list[str] = []
    res = fm_import.import_file(
        c,
        "test",
        FIX / "echt" / "2026-10-11_kader.csv",
        cfg or common.load_yaml("spalten.yaml"),
        warn=warnings.append,
    )
    return c, res, warnings


def test_echter_export_vollstaendig_gemappt():
    c, res, warnings = _import_echt()
    assert (res["rows"], res["unmapped"], res["unlesbar"]) == (3, 0, 0)
    assert warnings == []
    assert count(c, "player_attributes") == 3 * 47
    assert c.execute("SELECT COUNT(*) FROM player_attributes WHERE masked=1").fetchone()[0] == 0


def test_echter_export_werte():
    c, _, _ = _import_echt()

    def one(sql):
        row = c.execute(sql).fetchone()
        return row[0] if row else None

    def stat(name, uid):
        return one(f"SELECT value FROM player_stats WHERE player_uid='{uid}' AND stat='{name}'")

    def info(field, uid):
        return one(f"SELECT text FROM player_info WHERE player_uid='{uid}' AND field='{field}'")

    f, h, b = "92018043", "28121290", "2000183044"
    # Geld, Spannen, Daten
    assert one(f"SELECT wage FROM players WHERE player_uid='{h}'") == 997_000
    assert one(f"SELECT wage FROM players WHERE player_uid='{f}'") == pytest.approx(2_760_000)
    nums = c.execute(
        f"SELECT value_min, value_max, value, age FROM players WHERE player_uid='{f}'"
    ).fetchone()
    assert nums == pytest.approx((9e6, 11.5e6, 10.25e6, 33))
    dates = c.execute(
        f"SELECT contract_end, loan_end FROM players WHERE player_uid='{f}'"
    ).fetchone()
    assert dates == ("2028-06-30", "2027-06-30")
    assert one(f"SELECT loan_end FROM players WHERE player_uid='{h}'") is None  # "?"
    assert one(f"SELECT value FROM players WHERE player_uid='{b}'") is None
    assert info("value", b) == "Steht nicht zum Verkauf"
    # gemischte Dezimalzeichen
    assert stat("xgp", h) == 2.01 and stat("xg", f) == 3.68 and stat("npxg", f) == 1.18
    assert stat("wertung_avg", h) == 7.07 and stat("distanz_km", f) == 58.4
    # Einsätze "6 (2)" / "0 (3)", Quote, doppelte Header
    assert (stat("einsaetze_start_n", f), stat("einsaetze_ein_n", f)) == (6, 0)
    assert (stat("einsaetze_start_n", b), stat("einsaetze_ein_n", b)) == (0, 3)
    assert stat("kopfballduelle_gewonnen_pct", f) == pytest.approx(18 / 39 * 100)
    assert stat("kopfballduelle_gewonnen_pct", h) is None  # 0 Kopfbälle -> keine Quote
    assert stat("freistoesse", f) == 0
    assert one(
        f"SELECT value FROM player_attributes WHERE player_uid='{f}' AND attribute='Freistöße'"
    ) == 11
    # Text-/Datumsfelder
    assert info("nation", f) == "Deutschland" and info("vertragsbeginn", f) == "2024-08-05"
    assert info("verletzungsrisiko", f) == "Gering"


def test_echter_export_schutzchecks():
    cfg = common.load_yaml("spalten.yaml")
    cfg["gehalt"]["periode"] = "woche"  # Export sagt €/J. -> kein stilles ×52
    with pytest.raises(SystemExit):
        _import_echt(cfg)
    cfg = common.load_yaml("spalten.yaml")
    cfg["spalten"]["Größe"] = "birthdate"  # Text in einer Datumsspalte -> Abbruch
    with pytest.raises(SystemExit):
        _import_echt(cfg)


# --- per90 / value ----------------------------------------------------------------------------
def test_per90_threshold_and_percentiles(conn):
    cfg = common.load_yaml("rollen.yaml", CFG)
    players, _ = per90.load_wide(conn, "test")
    df = per90.compute_per90(players, cfg, "test_stuermer")
    assert df["n_klein"].any() and (~df["n_klein"]).any()
    assert df.loc[df["n_klein"], "npxg_p90_pctl"].isna().all()
    p = df["npxg_p90_pctl"].dropna()
    assert p.between(0, 100).all()
    first = df.iloc[0]
    assert first["npxg_p90"] == pytest.approx(first["npxg"] / first["minutes"] * 90)


def test_possession_adjustment(conn):
    cfg = common.load_yaml("rollen.yaml", CFG)
    players, _ = per90.load_wide(conn, "test")
    df = per90.compute_per90(players, cfg, "test_stuermer")
    r = df.iloc[0]
    assert r["pressing_p90"] == pytest.approx(
        r["pressing"] / r["minutes"] * 90 * 50 / r["team_possession"]
    )


def test_value_candidates(conn):
    cfg = common.load_yaml("rollen.yaml", CFG)
    players, attrs = per90.load_wide(conn, "test")
    df = value.candidates(players, attrs, cfg, "test_stuermer", max_alter=31)
    assert (df["age"] <= 31).all() and len(df) > 0
    assert df["rollen_score"].between(0, 100).all()
    assert df["value_pctl"].between(0, 100).all()
    assert (df["kosten_saison"] > df["wage"]).all()
    assert set(df["xg_flag"]) <= {"", "über xG", "unter xG"}


def test_value_missing_kpi_aborts(conn):
    cfg = common.load_yaml("rollen.yaml", CFG)
    cfg["rollen"]["test_stuermer"]["kpis"]["gibt_es_nicht_p90"] = 0.1
    players, attrs = per90.load_wide(conn, "test")
    with pytest.raises(SystemExit):
        value.candidates(players, attrs, cfg, "test_stuermer")


# --- team -------------------------------------------------------------------------------------
def test_team_kpis(conn):
    df = team.load_matches(conn, "test")
    kpis = team.kpi_columns(df)
    assert {"xg_for", "xg_against", "xg_diff"} <= set(kpis)
    r = team.rolling(df, kpis, 5)
    assert r["xg_for_roll5"].iloc[:4].isna().all() and r["xg_for_roll5"].iloc[4:].notna().all()
    assert team.summarize(df, kpis, "home_away")["spiele"].sum() == len(df)
    ba = team.before_after(df, kpis, "2027-02-15")
    assert ba.loc["spiele", "vorher"] + ba.loc["spiele", "nachher"] == len(df)


def test_resolve_save_env(monkeypatch):
    monkeypatch.setenv("FM27_SAVE", "foo")
    assert common.resolve_save() == "foo"
    assert common.resolve_save("bar") == "bar"
    monkeypatch.delenv("FM27_SAVE")
    assert common.resolve_save() == "werder"  # aus CLAUDE.md


def test_schema_is_sqlite():
    assert isinstance(common.connect(":memory:"), sqlite3.Connection)
    assert pd.__version__
