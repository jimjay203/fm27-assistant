"""Live-Import (FMMT-27-HTTP-Antwort) mit synthetischer Antwort, kein laufendes FM nötig."""

import common
import live
import pytest

CFG = common.load_yaml("live_spalten.yaml") | {"gehalt": {"periode": "woche", "faktor": 1.0}, "wert": {"faktor": 1.0}}
DERIVED = common.load_yaml("spalten.yaml").get("abgeleitet")
N_ATTR = len(CFG["attribute"])


def row(uid, name, club_id=1, owner_id=None, **kw):
    r = {
        "UID": uid, "Name": name, "Club": "Werder Bremen", "Division": "Bundesliga",
        "Position": "ST (C)", "Age": 24, "Mins": 900, "Wage": 10_000,
        "Transfer Value": "£1.5M", "Expires": "30/06/2029", "Team": "Senior Team",
        "Club ID": club_id, "Loaned From": "", "Loaned From ID": owner_id,
        "Gls": 5, "Drb/90": 2.0, "Ps C/90": 20.0, "Pas %": 80.0, "Hdrs W/90": 3.0, "Hdr %": 60.0,
        "Attrs": [50] * N_ATTR, "Personality": "", "Pos Ratings": [20] * 15,
    }  # fmt: skip
    return r | kw


def resp(*players):
    return {"ok": True, "date": "2026-12-04", "my_clubs": [{"name": "Werder", "uid": 1}],
            "rows": list(players), "players": len(players)}  # fmt: skip


def test_convert_p90_to_counts_and_quotes():
    c = live.convert_row(row(1, "A"), CFG, {"1"}, DERIVED)
    assert c["stats"]["dribblings"] == pytest.approx(20.0)  # 2.0 pro 90 * 900 / 90
    assert c["stats"]["paesse_angekommen"] == pytest.approx(200.0)
    assert c["stats"]["paesse_versucht"] == pytest.approx(250.0)  # 200 / 0.8
    assert c["stats"]["kopfballduelle_gewonnen_pct"] == pytest.approx(60.0)
    assert c["stats"]["tore"] == 5


def test_convert_money_date_wage():
    c = live.convert_row(row(1, "A"), CFG, {"1"})
    assert c["core"]["value"] == 1_500_000
    assert c["core"]["contract_end"] == "2029-06-30"
    assert c["core"]["wage"] == 520_000  # 10.000 pro Woche * 52


def test_placeholder_value_is_none():
    c = live.convert_row(row(1, "A", **{"Transfer Value": None}), CFG, {"1"})
    assert c["core"]["value"] is None


def test_attrs_only_for_own_players_and_scaled():
    own = live.convert_row(row(1, "Eigen"), CFG, {"1"})
    assert own["own"] and set(own["attrs"].values()) == {10.0}  # 50 / 5
    assert len(own["attrs"]) == N_ATTR
    loaned_out = live.convert_row(row(2, "Verliehen", club_id=9, owner_id=1), CFG, {"1"})
    assert loaned_out["own"] and loaned_out["attrs"]
    foreign = live.convert_row(row(3, "Fremd", club_id=9), CFG, {"1"})
    assert not foreign["own"] and foreign["attrs"] is None


def test_no_hidden_fields_leak():
    c = live.convert_row(row(1, "A", CA=150, PA=180, Personality="Fiery"), CFG, {"1"})
    assert set(c["core"]) == {
        "name", "club", "league", "position", "age", "minutes", "wage", "value", "contract_end"
    }  # fmt: skip
    assert set(c["info"]) <= {"quelle", "team", "ausgeliehen_von", "eigen"}
    gespeichert = set(c["stats"].values()) | set(c["attrs"].values())
    assert 150 not in gespeichert and 180 not in gespeichert


def test_zero_minutes_skips_p90_stats():
    c = live.convert_row(row(1, "A", Mins=0), CFG, {"1"})
    assert "dribblings" not in c["stats"]


def test_import_replaces_snapshot_and_stores_view():
    conn = common.connect(":memory:")
    r = resp(row(1, "Eigen"), row(3, "Fremd", club_id=9))
    quiet = lambda m: None
    live.import_live(conn, "test", r, CFG, quiet, DERIVED)
    res = live.import_live(conn, "test", r, CFG, quiet, DERIVED)  # erneut: kein Duplikat
    assert res["spieler"] == 2 and res["eigene"] == 1 and res["mit_attr"] == 1
    assert conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT view_type FROM snapshots").fetchone()[0] == "live"
    assert conn.execute("SELECT COUNT(*) FROM player_attributes").fetchone()[0] == N_ATTR
    assert conn.execute("SELECT value FROM players WHERE player_uid='1'").fetchone()[0] == 1_500_000


def test_import_requires_calibrated_wage_period():
    conn = common.connect(":memory:")
    uncal = CFG | {"gehalt": {"periode": None, "faktor": 1.0}}
    with pytest.raises(SystemExit):
        live.import_live(conn, "test", resp(row(1, "A")), uncal, lambda m: None)


def test_club_country_filled_from_earlier_snapshot():
    conn = common.connect(":memory:")
    conn.execute("INSERT INTO snapshots VALUES(1,'test','2026-11-20','x.csv','kader','t')")
    conn.execute(
        "INSERT INTO players(snapshot_id, player_uid, club, club_country) "
        "VALUES(1,'99','Werder Bremen','Deutschland')"
    )
    live.import_live(conn, "test", resp(row(1, "A")), CFG, lambda m: None, DERIVED)
    got = conn.execute("SELECT club_country FROM players WHERE player_uid='1'").fetchone()[0]
    assert got == "Deutschland"


def test_non_senior_players_keep_profile_but_no_stats_or_minutes():
    reserve = live.convert_row(row(5, "Reserve", Team="Reserves"), CFG, {"1"})
    blank = live.convert_row(row(6, "Leer", Team=""), CFG, {"1"})
    for c in (reserve, blank):
        assert c["stats"] == {} and c["core"]["minutes"] is None
        assert c["core"]["value"] == 1_500_000 and c["core"]["contract_end"] == "2029-06-30"
    assert blank["info"]["team"] == "unbekannt" and reserve["info"]["team"] == "Reserves"
    senior = live.convert_row(row(7, "Profi"), CFG, {"1"})
    assert senior["stats"] and senior["core"]["minutes"] == 900


def test_fork_fields_squad_role_and_morale_stored_as_info():
    own = live.convert_row(row(1, "Eigen", **{"Squad Role": "Stammspieler", "Morale": 66}), CFG, {"1"})
    assert own["info"]["rolle"] == "Stammspieler" and own["info"]["moral_wert"] == "66"
    loan_in = live.convert_row(
        row(2, "Leihe", owner_id=9, **{"Squad Role": None, "Morale": None}), CFG, {"1"}
    )
    assert "rolle" not in loan_in["info"] and "moral_wert" not in loan_in["info"]
    plain = live.convert_row(row(3, "OhneFork"), CFG, {"1"})  # Original-FMMT liefert die Felder nicht
    assert "rolle" not in plain["info"] and "moral_wert" not in plain["info"]
