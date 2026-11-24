"""Datenfehler 17.07.2027: eigene Spieler ohne passende Position (Arthur, Umschulung RV -> OM r) und veraltete
Vereinsangaben aus der Vorsaison (Dinkçi, Manneh)."""

import copy

import benchmark as b
import common
import ligen
import pandas as pd
import per90
import planer
import rollen
from conftest import MINI_FORMATIONEN, mini_df, mini_rk

W = "Werder Bremen"


# --------------------------------------------------------------------------- Vereinsangaben (per90.aktueller_stand)


def _db():
    """Vorsaison: Kader 31.05. + Suche 31.05.; laufende Saison: Kader 14.07., Suche 14.07., Kader 17.07."""
    conn = common.connect(":memory:")
    snaps = [(1, "2027-05-31", "kader"), (2, "2027-05-31", "suche"), (3, "2027-07-14", "kader"),
             (4, "2027-07-14", "suche"), (5, "2027-07-17", "kader")]  # fmt: skip
    for sid, d, v in snaps:
        conn.execute("INSERT INTO snapshots VALUES(?, 'w', ?, ?, ?, 'x')", (sid, d, f"f{sid}", v))
    spieler = [  # (snapshot, uid, club, minutes, value, loan_end)
        (1, "eigen", W, 2000, 2e6, None),
        (
            1,
            "dinkci",
            W,
            1447,
            2.3e6,
            "2027-06-30",
        ),  # Leihe an uns vorbei, in keiner aktuellen Quelle
        (1, "mbangula", W, 1500, 9e6, None),  # im Kader 14.07., nicht mehr im Kader 17.07.
        (2, "manneh", "Cercle Brugge", 2850, 1e6, "2027-06-30"),
        (2, "kand", "Y", 2500, 3e6, None),  # nur in der Suche der Vorsaison
        (3, "eigen", W, 0, 2e6, None),
        (3, "mbangula", W, 0, 9e6, None),
        (3, "manneh", W, 0, 9.3e6, None),
        (4, "fremd", "Z", 900, 4e6, None),
        (5, "eigen", W, 0, 2.5e6, None),
        (5, "manneh", W, 0, 9.3e6, None),
    ]
    for sid, uid, club, m, v, ende in spieler:
        conn.execute(
            "INSERT INTO players(snapshot_id, player_uid, name, club, league, club_country, position, "
            "minutes, value, loan_end) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sid, uid, uid, club, "Bundesliga", "Deutschland", "ST (Z)", m, v, ende),
        )
        conn.execute("INSERT INTO player_stats VALUES(?,?,'tore',?)", (sid, uid, 1.0))
    return conn


def test_neuester_stand_aus_allen_quellen_der_laufenden_saison():
    d = per90.load_saison(_db(), "w")[0].set_index("player_uid")
    assert d.loc["manneh", "club"] == W and d.loc["manneh", "value"] == 9.3e6
    assert pd.isna(d.loc["manneh", "stand_datum"]) and pd.isna(d.loc["eigen", "stand_datum"])
    assert d.loc["manneh", "club_vs"] == "Cercle Brugge"  # Statistik-Verein der Vorsaison bleibt
    assert d.loc["manneh", "minutes"] == 2850  # Statistik unverändert aus der Vorsaison
    # nur Suche gewählt: Verein trotzdem vom neueren Kader-Export (vorher: Cercle Brugge aus der Vorsaison)
    s = per90.load_saison(_db(), "w", views=("suche",))[0].set_index("player_uid")
    assert s.loc["manneh", "club"] == W and s.loc["manneh", "value"] == 9.3e6


def test_ehemaliger_eigener_spieler_heisst_verein_unbekannt():
    d = per90.load_saison(_db(), "w")[0].set_index("player_uid")
    assert d.loc["dinkci", "club"] == (
        "Verein unbekannt (zuletzt Werder Bremen, Leihe bis 30.06.2027; Stand 31.05.2027)"
    )
    assert d.loc["mbangula", "club"] == "Verein unbekannt (zuletzt Werder Bremen; Stand 14.07.2027)"
    assert d.loc["dinkci", "stand_datum"] == "2027-05-31"
    assert d.loc["dinkci", "club_roh"] is None  # zählt in keiner Vereinsgruppe (Topclubs)
    assert d.loc["dinkci", "league"] == "Bundesliga"  # Liga für das Liga-Gewicht bleibt


def test_fremder_spieler_nur_in_der_vorsaison_mit_stand_datum():
    d = per90.load_saison(_db(), "w")[0].set_index("player_uid")
    assert d.loc["kand", "club"] == "Y (Stand 31.05.2027)" and d.loc["kand", "club_roh"] == "Y"
    assert d.loc["fremd", "club"] == "Z" and pd.isna(d.loc["fremd", "stand_datum"])


def test_load_db_fuehrt_ehemalige_nicht_als_eigene():
    df = b.load_db(_db(), "w", eigene=True).set_index("uid")
    assert set(df.index[df["own"]]) == {"eigen", "manneh"}
    assert not df.loc["dinkci", "own"] and not df.loc["mbangula", "own"]
    assert df.loc["dinkci", "club"].startswith("Verein unbekannt (zuletzt Werder Bremen")


def test_topclubs_ohne_stand_kennzeichnung():
    df = pd.DataFrame({"club": ["A (Stand 31.05.2027)", "A", "B"], "club_roh": ["A", "A", "B"],
                       "value": [10.0, 10.0, 15.0], "team": "Senior Team"})  # fmt: skip
    assert b.topclub_liste(df, 1) == ["A"]


def test_verein_unbekannt_text():
    assert per90.verein_unbekannt_text(W) == "Verein unbekannt (zuletzt Werder Bremen)"
    assert per90.verein_unbekannt_text(W, "2027-06-30", "2027-05-31") == (
        "Verein unbekannt (zuletzt Werder Bremen, Leihe bis 30.06.2027; Stand 31.05.2027)"
    )


# --------------------------------------------------------------------------- Eigene Spieler ohne passende Position


def _df_mit_arthur():
    """mini_df + eigener Spieler 'Arthur' als RV (Position passt nicht zur Gruppe st) und fremder 'Arthur Fremd'."""
    extra = pd.DataFrame({
        "uid": ["AR", "AF"], "name": ["Arthur", "Arthur Fremd"], "position": ["V/FV (R)", "ST (Z)"],
        "minutes": 3130, "team": "Senior Team", "datenbasis": "voll", "league": "Bundesliga",
        "x": [40.0, 60.0], "f": [60.0, 40.0], "club": ["Wir", "Andere"], "age": 24, "value": 12e6,
        "own": [True, False], "eigen": ["kader", None], "in_suche": [False, True],
    })  # fmt: skip
    return pd.concat([mini_df(), extra], ignore_index=True)


def test_stamm_maske_ganzer_name_oder_nachname():
    namen = pd.Series(["Arthur", "Marco Grüll", "Arthur Vermeeren", "José Córdoba"])
    assert rollen.stamm_maske(namen, ["Arthur", "Grull", "cordoba"]).tolist() == [
        True,
        True,
        False,
        True,
    ]
    assert not rollen.stamm_maske(namen, None).any()


def test_detail_treffer_eigene_und_exakter_name_zuerst():
    df = _df_mit_arthur()
    assert rollen.detail_treffer(df, "Arthur") == ({"AR"}, "eigener Spieler, exakter Name")
    assert rollen.detail_treffer(df, "arthur fremd") == ({"AF"}, "fremder Spieler, exakter Name")
    assert rollen.detail_treffer(df, "Kandidat 39")[0] == {"k39"}  # exakt schlägt "Kandidat 390"
    assert rollen.detail_treffer(df, "Kandidat 39")[1] == "fremder Spieler, exakter Name"
    assert {"k39", "k390"} <= rollen.detail_treffer(df, "andidat 39")[0]  # sonst Teiltreffer
    assert rollen.detail_treffer(df, "gibtsnicht") == (set(), "kein Treffer")


def _ctx(df=None, slots_taktik=None, formationen=None):
    return planer.kontext_bauen(
        _df_mit_arthur() if df is None else df, mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900},
        formationen or MINI_FORMATIONEN, slots_taktik,
    )  # fmt: skip


def test_stammspieler_ohne_passende_position_wird_im_slot_bewertet():
    ctx = _ctx()
    _, _, own, cand = planer.slot_bewerten(ctx, "Mit", "Ohne", planer.Filter())
    assert "AR" not in set(own["uid"])  # ohne Stamm-Eintrag wie bisher: Position passt nicht
    _, _, own, cand = planer.slot_bewerten(ctx, "Mit", "Ohne", planer.Filter(), stamm=["Arthur"])
    r = own.set_index("uid").loc["AR"]
    assert r["pos_hinweis"] == rollen.POS_NICHT_GELISTET and pd.notna(r["paar"])
    assert pd.isna(own.set_index("uid").loc["A", "pos_hinweis"])
    assert "AR" not in set(cand["uid"]) and "AF" in set(
        cand["uid"]
    )  # fremde nie über den Stamm-Namen


def test_plan_nutzt_stamm_aus_taktik_slots():
    form = copy.deepcopy(MINI_FORMATIONEN)
    form["formationen"]["2er"]["vorbelegung_aus"] = "taktik_slots.yaml"
    ctx = _ctx(
        slots_taktik={"ST r": {"mit": "Mit", "ohne": "Ohne", "stamm": ["Arthur"]}}, formationen=form
    )
    p = planer.plan(ctx, "2er", {}, planer.Filter())
    r = [z for z in p["slots"]["ST r"]["eigene"] if z["uid"] == "AR"]
    assert r and r[0]["pos_hinweis"] == "Position nicht gelistet"
    assert "AR" not in {
        z["uid"] for z in p["slots"]["ST l"]["eigene"]
    }  # nur im Slot mit Stamm-Eintrag


def test_suche_findet_eigenen_spieler_per_name_auch_ohne_position():
    ctx = _ctx()
    r = planer.suche(ctx, "Mit", "Ohne", planer.Suche(text="arthur"))
    t = {z["uid"]: z for z in r["treffer"]}
    assert t["AR"]["pos_hinweis"] == "Position nicht gelistet" and t["AR"]["eigen"] == "kader"
    assert "AF" in t


def test_suche_ohne_treffer_stuerzt_nicht_ab():
    r = planer.suche(_ctx(), "Mit", "Ohne", planer.Suche(text="gibtsnicht"))
    assert r["treffer"] == [] and r["n_treffer"] == 0
