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
    assert fmparse.parse_money("2,76Mio. €/J.", decimal=",") == pytest.approx(2_760_000)  # NBSP
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


def _import_echt(cfg=None, datei="2026-10-11_kader.csv"):
    c = common.connect(":memory:")
    warnings: list[str] = []
    res = fm_import.import_file(
        c,
        "test",
        FIX / "echt" / datei if isinstance(datei, str) else datei,
        cfg or common.load_yaml("spalten.yaml"),
        warn=warnings.append,
    )
    return c, res, warnings


def test_echter_export_vollstaendig_gemappt():
    c, res, warnings = _import_echt()
    assert (res["rows"], res["unmapped"], res["unlesbar"]) == (6, 0, 0)
    assert warnings == []  # auch: einzelnes "Endet" (Kader) löst keine Doppel-Header-Warnung aus
    assert count(c, "player_attributes") == 6 * 47
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
    assert one(f"SELECT club_country FROM players WHERE player_uid='{f}'") == "Deutschland"
    dates = c.execute(
        f"SELECT contract_end, loan_start, loan_end FROM players WHERE player_uid='{f}'"
    ).fetchone()
    assert dates == ("2028-06-30", "2026-07-06", "2027-06-30")  # Leihdauer "6.7.26 - 30.6.27"
    assert info("ausgeliehen_von", f) == "West Ham"
    assert one(f"SELECT loan_end FROM players WHERE player_uid='{h}'") is None  # Leihdauer "-"
    assert info("ausgeliehen_von", h) is None
    # an Münster verliehen: Verein/Liga sind die des Leihvereins, Stammverein = Werder
    adeh = c.execute(
        "SELECT club, league, loan_start, loan_end FROM players WHERE player_uid='2000327143'"
    ).fetchone()
    assert adeh == ("Münster", "3. Liga", "2026-07-01", "2027-06-30")
    assert info("ausgeliehen_von", "2000327143") == "Werder Bremen"
    assert info("rolle", "2000327143") == "Verliehen"
    # Jugendvertrag: Gehalt 3,3K, Transferwert-Spanne ab 0 €
    jung = c.execute(
        "SELECT wage, value_min, value_max FROM players WHERE player_uid='2000475076'"
    ).fetchone()
    assert jung == pytest.approx((3300, 0, 24000))
    assert info("vertragsstatus", "2000475076") == "Jugendvertrag"
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


SUCHE = "2026-10-11_suche_stuermer.csv"  # Spielersuche: andere Spalten, Scouting-Spannen


def test_suche_vollstaendig_gemappt():
    c, res, warnings = _import_echt(datei=SUCHE)
    assert (res["rows"], res["unmapped"], res["unlesbar"]) == (4, 0, 0)
    assert warnings == []
    assert count(c, "player_attributes") == 4 * 47


def test_suche_leihe_endet_und_stammverein():
    c, _, _ = _import_echt(datei=SUCHE)
    row = c.execute(
        "SELECT p.club, p.contract_end, p.loan_start, p.loan_end, i.text FROM players p "
        "JOIN player_info i ON i.player_uid=p.player_uid AND i.field='ausgeliehen_von' "
        "WHERE p.player_uid='19112560'"
    ).fetchone()
    # Suche: 2. "Endet" = Leihende, keine Leihdauer -> loan_start leer
    assert row == ("Bahia", "2026-12-31", None, "2026-12-31", "Fluminense")
    # kein Leihspieler -> weder Leihende noch Stammverein
    assert c.execute(
        "SELECT loan_end FROM players WHERE player_uid='19266403'"
    ).fetchone() == (None,)


def test_suche_spannen_und_texte():
    c, _, _ = _import_echt(datei=SUCHE)

    def one(sql):
        row = c.execute(sql).fetchone()
        return row[0] if row else None

    def attr(uid, name):
        return c.execute(
            f"SELECT value, masked, lo, hi FROM player_attributes "
            f"WHERE player_uid='{uid}' AND attribute='{name}'"
        ).fetchone()

    cabral, egg, braith = "19266403", "91143690", "27013113"
    # Gehalts- und Wertspanne ("456K € – 742K € /J.")
    w = c.execute(f"SELECT wage, wage_min, wage_max FROM players WHERE player_uid='{cabral}'")
    assert w.fetchone() == pytest.approx((599_000, 456_000, 742_000))
    # Scouting-Spanne: Wert NULL, Grenzen bleiben erhalten; "-" = völlig verdeckt
    assert attr(cabral, "Abschluss") == (None, 1, 11.0, 15.0)
    assert attr(cabral, "Weite Einwürfe") == (None, 1, None, None)
    # gescoutet: exakter Wert, lo = hi
    assert attr(egg, "Abschluss") == (14.0, 0, 14.0, 14.0)
    # doppelte Header auch bei geänderter Attribut-Reihenfolge: Stat vs. Attribut
    assert attr(egg, "Freistöße")[0] == 10
    assert one(
        f"SELECT value FROM player_stats WHERE player_uid='{egg}' AND stat='freistoesse'"
    ) == 0
    # neue Textspalten; '–' (Ablöseforderung) = leer -> kein Eintrag
    info = lambda f, u: one(f"SELECT text FROM player_info WHERE player_uid='{u}' AND field='{f}'")  # noqa: E731
    assert info("geburtsland", braith) == "Dänemark" and info("vertragsart", braith) == "Vollzeitvertrag"
    assert info("abloeseforderung", braith) is None
    assert info("eigengewaechs", cabral) is None and info("eigengewaechs", egg) is not None
    assert info("value", braith) == "Steht nicht zum Verkauf"
    assert one(f"SELECT value FROM players WHERE player_uid='{braith}'") is None
    # Land des Vereins ("Ansässig in") trennt die österreichische von der deutschen Bundesliga
    club = lambda u: c.execute(  # noqa: E731
        f"SELECT league, club_country FROM players WHERE player_uid='{u}'"
    ).fetchone()
    assert club(egg) == ("Bundesliga", "Österreich") and club(cabral)[1] == "Brasilien"


def test_liga_ranking_nach_liga_und_land():
    c = common.connect(":memory:")
    cfg = common.load_yaml("ligen.yaml")
    n_strength, n_ranking = fm_import.load_leagues(c, cfg)
    assert n_ranking == len(cfg["ranking"]) > 74 and n_strength == 0
    # Stufen steigen in Listenreihenfolge monoton (Herausragend ... Durchschnittlich)
    stufen = list(dict.fromkeys(e["ansehen"] for e in cfg["ranking"]))
    assert stufen[:5] == ["Herausragend", "Exzellent", "Beeindruckend", "Gut", "Recht gut"]
    assert stufen == sorted(stufen, key=stufen.index)  # jede Stufe bildet einen zusammenhängenden Block
    assert [e["ansehen"] for e in cfg["ranking"]] == sorted(
        (e["ansehen"] for e in cfg["ranking"]), key=stufen.index
    )

    def rang(liga, land):
        row = c.execute(
            "SELECT rang, ansehen FROM league_ranking WHERE league=? AND country=?", (liga, land)
        ).fetchone()
        return row

    # gleichnamige Ligen sind getrennt
    assert rang("Bundesliga", "Deutschland") == (4, "Exzellent")
    assert rang("Bundesliga", "Österreich") == (21, "Beeindruckend")
    assert rang("Super League", "Griechenland")[0] < rang("Super League", "Schweiz")[0]
    assert rang("3. Liga", "Deutschland")[1] == "Brauchbar"
    assert rang("2. Bundesliga", "Deutschland")[0] < rang("3. Liga", "Deutschland")[0]
    # Neuladen ersetzt statt zu verdoppeln
    fm_import.load_leagues(c, cfg)
    assert count(c, "league_ranking") == n_ranking


def test_liga_ranking_doppelt_bricht_ab():
    c = common.connect(":memory:")
    e = {"liga": "X", "land": "Y"}
    with pytest.raises(SystemExit):
        fm_import.load_leagues(c, {"ranking": [e, dict(e)]})


def test_ranking_join_und_warnung():
    c = common.connect(":memory:")
    fm_import.load_leagues(c, common.load_yaml("ligen.yaml"))
    cfg, warnings = common.load_yaml("spalten.yaml"), []
    for f in ("2026-10-11_kader.csv", SUCHE):
        fm_import.import_file(c, "test", FIX / "echt" / f, cfg, warn=warnings.append)
    # Kader enthält "RL Nord", das nicht in der Ranking-Liste steht (dort nur "Regionalliga"); die Suche passt
    assert len(warnings) == 1
    assert "RL Nord (Deutschland)" in warnings[0]
    assert "3. Liga" not in warnings[0] and "Bundesliga" not in warnings[0]
    players, _ = per90.load_wide(c, "test")
    r = players.set_index("name")[["liga_rang", "liga_ansehen"]]
    assert tuple(r.loc["Niclas Füllkrug"]) == (4, "Exzellent")  # Bundesliga Deutschland
    assert tuple(r.loc["Johannes Eggestein"]) == (21, "Beeindruckend")  # Bundesliga Österreich
    assert "liga_rang_p90" not in players  # Kernspalte, kein Stat
    # Liga fehlt im Ranking -> Warnung
    c.execute("DELETE FROM league_ranking WHERE league='Brasileirão'")
    w2: list[str] = []
    fm_import.import_file(c, "test", FIX / "echt" / SUCHE, cfg, warn=w2.append)
    assert any("Brasileirão (Brasilien)" in w for w in w2)


def test_doppelter_header_nur_einmal_warnt(tmp_path):
    text = (FIX / "echt" / "2026-10-11_kader.csv").read_text(encoding="utf-8")
    head, rest = text.split("\n", 1)
    head = ",Freistöße,".join(head.split(",Freistöße,")[:-1]) + ",Fremd," + head.rsplit(
        ",Freistöße,", 1
    )[1]
    f = tmp_path / "2026-10-11_kader.csv"
    f.write_text(head + "\n" + rest, encoding="utf-8")
    _, res, warnings = _import_echt(datei=f)
    assert any("kommt nur einmal vor" in w and "Freistöße" in w for w in warnings)
    assert res["unmapped"] == 1  # 'Fremd'


def test_migration_alter_db(tmp_path):
    p = tmp_path / "alt.sqlite"
    raw = sqlite3.connect(p)
    raw.execute(
        "CREATE TABLE player_attributes(snapshot_id INTEGER NOT NULL, player_uid TEXT NOT NULL, "
        "attribute TEXT NOT NULL, value REAL, masked INTEGER NOT NULL DEFAULT 0, "
        "PRIMARY KEY(snapshot_id, player_uid, attribute))"
    )
    raw.commit()
    raw.close()
    c = common.connect(p)
    cols = {r[1] for r in c.execute("PRAGMA table_info(player_attributes)")}
    assert {"lo", "hi"} <= cols
    assert {"wage_min", "wage_max"} <= {r[1] for r in c.execute("PRAGMA table_info(players)")}


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


def test_percentile_groups_split_by_club_country():
    df = pd.DataFrame(
        {
            "position": ["ST"] * 4,
            "league": ["Bundesliga"] * 4,
            "club_country": ["Deutschland", "Deutschland", "Österreich", "Österreich"],
            "x": [1.0, 2.0, 3.0, 4.0],
        }
    )
    pool = pd.Series(True, index=df.index)
    got = per90.percentile_in_groups(df, "x", pool, min_group=2)
    assert got.tolist() == [50.0, 100.0, 50.0, 100.0]  # nicht 25/50/75/100 über beide Länder


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
