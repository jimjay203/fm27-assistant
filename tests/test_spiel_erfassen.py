"""Spiele aus Spielbericht-Werten (spiel_erfassen.py), Namen-Abgleich live (namen.py), Liga-Stufe des Zielvereins."""

import textwrap

import benchmark as b
import common
import ligen
import namen
import pandas as pd
import pytest
import rollen
import rollen_attr
import spiel_erfassen as se
import spiele
import team

LG = ligen.Ligen.laden()

YAML = textwrap.dedent(
    """\
    datum: 2027-08-21
    gegner: RB Leipzig
    ort: Auswärts
    wettbewerb: Bundesliga
    taktik_slot: Standard
    saison: 2027/28
    werte:
      tore: [2, 1]
      ballbesitz: [47, 53]
      schuesse: [11, 11]
      schuesse_aufs_tor: [5, 4]
      xg: ["2,29", 1.75]
      ppda: [16.23, 14.64]
      grosschancen: [2, 2]
      ecken: [12, 8]
      prog_paesse: [46, 63]
      passquote: [88, 89]
      flankenquote: [12, 30]
      fouls: [5, 9]
      gelb: [1, 3]
      rot: [0, 1]
      laufleistung: [122, 119]
      notenschnitt: [6.8, 6.7]
    aufstellung:
      - {slot: TW, rolle: TW, spieler: Hein, note: 6.9}
      - {slot: RV, rolle: IFV, spieler: Keidel, note: 6.5}
      - {slot: IV l, rolle: IV, spieler: Cordoba, note: 6.5}
      - {slot: ST, rolle: HRS, spieler: Manneh, note: 7.0, tore: 1}
      - {spieler: Itten, einwechslung: true, tore: 1}
    """
)


def db(tmp_path):
    """Zwei Kader-Exporte: Itten nur im älteren (abgegeben), Grüll in beiden."""
    conn = common.connect(tmp_path / "t.sqlite")
    kader = {
        "2027-07-17": {"1": "Karl Hein", "2": "Felix Keidel", "3": "José Córdoba", "4": "Abdoulie Manneh",
                       "5": "Cedric Itten", "6": "Marco Grüll"},
        "2027-09-04": {"1": "Karl Hein", "2": "Felix Keidel", "3": "José Córdoba", "4": "Abdoulie Manneh",
                       "6": "Marco Grüll"},
    }  # fmt: skip
    for d, spieler in kader.items():
        sid = conn.execute(
            "insert into snapshots(save, ingame_date, source_file, view_type, imported_at) values(?,?,?,?,?)",
            ("t", d, f"{d}_kader.csv", "kader", "x"),
        ).lastrowid
        for uid, name in spieler.items():
            conn.execute(
                "insert into players(snapshot_id, player_uid, name) values(?,?,?)", (sid, uid, name)
            )
    conn.commit()
    return conn


def datei(tmp_path, text=YAML, name="2027-08-21_spiel_leipzig.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_spiel_landet_in_team_tabellen_mit_namen_wie_der_export(tmp_path):
    conn = db(tmp_path)
    r = se.erfassen(conn, "t", datei(tmp_path), warn=lambda m: None)
    assert r["einsaetze"] == 5
    m = conn.execute(
        "select ingame_date, opponent, home_away, tactic_slot, competition, xg_for, xg_against, goals_for, "
        "goals_against, possession, shots_for, shots_against from team_matches"
    ).fetchall()
    assert m == [
        ("2027-08-21", "RB Leipzig", "A", "Standard", "Bundesliga", 2.29, 1.75, 2, 1, 47, 11, 11)
    ]
    stats = dict(conn.execute("select stat, value from team_match_stats").fetchall())
    # gleiche Stat-Namen wie die Spiel-Exporte (config/spalten.yaml, Teamdatei)
    export_namen = {
        v for v in common.load_yaml("spalten.yaml")["spalten"].values() if isinstance(v, str)
    }
    assert set(stats) <= export_namen and len(stats) == 24
    assert stats["ppda_for"] == pytest.approx(16.23) and stats["red_against"] == 1
    assert team.load_matches(conn, "t")["xg_diff"].iloc[0] == pytest.approx(0.54)


def test_aufstellung_mit_positionen_rollen_und_abgegebenem_spieler(tmp_path):
    conn = db(tmp_path)
    se.erfassen(conn, "t", datei(tmp_path), warn=lambda m: None)
    df = spiele.einsaetze(conn, "t").set_index("player_uid")
    assert df.loc["2", "position"] == "V (R)" and df.loc["2", "rolle_kurz"] == "IFV"
    assert df.loc["3", "position"] == "V (Z)"  # Seitenbit IV l zählt nicht als eigene Position
    assert df.loc["4", "rolle"] == "Halbraumstürmer" and df.loc["4", "tore"] == 1
    assert df.loc["5", "einwechslung"] == 1 and pd.isna(
        df.loc["5", "position"]
    )  # Itten: älterer Export
    assert df.loc["1", "wettbewerb"] == 16 and pd.isna(df.loc["1", "minuten"])


def test_erneut_erfassen_ersetzt_ohne_duplikate_und_schuetzt_fm27_daten(tmp_path):
    conn = db(tmp_path)
    p = datei(tmp_path)
    se.erfassen(conn, "t", p, warn=lambda m: None)
    conn.execute(
        "update spieleinsaetze set roh='00ff', note=7.7 where player_uid='1'"
    )  # wie aus spiele.py
    conn.commit()
    weniger = YAML.replace("  - {spieler: Itten, einwechslung: true, tore: 1}\n", "")
    p.write_text(weniger, encoding="utf-8")
    warnungen = []
    se.erfassen(conn, "t", p, warn=warnungen.append)
    assert conn.execute("select count(*) from team_matches").fetchone()[0] == 1
    assert conn.execute("select count(*) from snapshots where view_type='spiel'").fetchone()[0] == 1
    uids = {u for (u,) in conn.execute("select player_uid from spieleinsaetze")}
    assert uids == {"1", "2", "3", "4"}  # Itten entfernt
    assert conn.execute("select note from spieleinsaetze where player_uid='1'").fetchone()[0] == 7.7
    assert any("Hein" in w for w in warnungen)
    se.erfassen(conn, "t", p, ueberschreiben=True, warn=lambda m: None)
    assert conn.execute("select note from spieleinsaetze where player_uid='1'").fetchone()[0] == 6.9


def test_fehler_werden_benannt(tmp_path):
    conn = db(tmp_path)
    with pytest.raises(ValueError, match="saison"):
        se.erfassen(
            conn, "t", datei(tmp_path, YAML.replace("2027/28", "2026/27")), warn=lambda m: None
        )
    with pytest.raises(ValueError, match="Unbekannt"):
        se.erfassen(conn, "t", datei(tmp_path, YAML.replace("spieler: Hein", "spieler: Unbekannt")),
                    warn=lambda m: None)  # fmt: skip
    with pytest.raises(ValueError, match="XYZ"):
        se.erfassen(
            conn,
            "t",
            datei(tmp_path, YAML.replace("rolle: HRS", "rolle: XYZ")),
            warn=lambda m: None,
        )
    assert (
        conn.execute("select count(*) from team_matches").fetchone()[0] == 0
    )  # nichts halb geschrieben


def test_alle_slots_aus_taktik_slots_haben_positionsbits():
    for slot in common.load_yaml("taktik_slots.yaml")["slots"]:
        assert se.SLOT_ALIAS.get(slot, slot) in se.SLOT_BITS, slot


# --------------------------------------------------------------------------- Namen live


def test_live_namen_werden_ueber_uid_auf_exportnamen_gesetzt(tmp_path):
    conn = db(tmp_path)
    export = namen.export_namen(conn, "t")
    live = pd.DataFrame({"uid": ["6", "9", "8"], "name": ["Marco Benke", "Neuer Spieler", "Max Fake"],
                         "own": [True, True, False]})  # fmt: skip
    alias = {"uid": {}, "name": {namen.name_norm("Max Fake"): "Max Echt"}}
    out = namen.angleichen(live, export, alias)
    assert out["name"].tolist() == ["Marco Grüll", "Neuer Spieler", "Max Echt"]
    assert out["name_live"].tolist() == ["Marco Benke", "Neuer Spieler", "Max Fake"]
    assert [x["live"] for x in out.attrs["namen_abweichend"] if x["own"]] == ["Marco Benke"]
    # taktik_slots.yaml (stamm) und --detail finden Grüll über den Exportnamen, auch über den Live-Namen
    assert rollen.stamm_maske(out["name"], ["Grüll"]).tolist() == [True, False, False]
    assert rollen.stamm_maske(live["name"], ["Benke"], None).tolist() == [True, False, False]
    assert rollen.detail_treffer(out.assign(own=True), "Benke")[0] == {"6"}
    assert namen.alias_laden()["uid"]["16195163"] == "Marco Grüll"  # produktive Alias-Datei


def test_uid_fuer_name_sucht_im_neuesten_export_mit_dem_namen(tmp_path):
    conn = db(tmp_path)
    assert namen.uid_fuer_name(conn, "t", "Itten") == [("5", "Cedric Itten", "2027-07-17")]
    assert namen.uid_fuer_name(conn, "t", "córdoba")[0][0] == "3"
    assert namen.uid_fuer_name(conn, "t", "Niemand") == []


# --------------------------------------------------------------------------- Liga-Stufe Zielverein


def test_ziel_stufe_nur_aus_eigenem_profikader():
    # live: Leihspieler (Liga des Leihvereins) und Jugend/Reserve dürfen die Stufe nicht kippen
    df = pd.DataFrame({
        "own": True,
        "eigen": ["kader"] * 3 + ["leihe_aus"] * 4 + ["kader"] * 4,
        "team": ["Senior Team"] * 7 + ["U19"] * 4,
        "league": ["Bundesliga"] * 3 + ["2. Bundesliga"] * 4 + ["Regionalliga Nord"] * 4,
    })  # fmt: skip
    assert rollen_attr.ziel_liga(df, LG) == ("Bundesliga", "Exzellent", 3)
    assert (
        rollen_attr.ziel_stufe(df.drop(columns=["eigen", "team"]), LG) == "Gut"
    )  # bisher: Leihen + Jugend kippen die Stufe


def test_liga_mit_land_auch_fuer_live_namen_mit_sponsor():
    assert LG.stufe("ADMIRAL Bundesliga (Österreich)") == "Beeindruckend"
    assert LG.stufe("Bundesliga (Deutschland)") == "Exzellent"
    assert LG.stufe("Bundesliga (Österreich)") == "Beeindruckend"
    assert LG.stufe("Oberliga Hamburg (Deutschland)") == "Durchschnittlich"
    assert (
        LG.stufe("ADMIRAL 2. Liga (Deutschland)") is None
    )  # Land widerspricht dem Alias, Liga dort unbekannt


def test_live_tabelle_bekommt_land_und_exportnamen(tmp_path):
    conn = db(tmp_path)
    sid = conn.execute("select max(id) from snapshots").fetchone()[0]
    conn.execute(
        "update players set club='Werder Bremen', club_country='Deutschland' where snapshot_id=?",
        (sid,),
    )
    live = pd.DataFrame({"uid": ["6", "7"], "name": ["Marco Benke", "X"], "own": [True, False],
                         "club": ["Werder Bremen", "Rapid Wien"], "league": ["Bundesliga", "ADMIRAL Bundesliga"]})  # fmt: skip
    live.attrs["date"] = "2027-09-05"
    out = b.live_angleichen(live, conn, "t")
    assert out["league"].tolist() == ["Bundesliga (Deutschland)", "ADMIRAL Bundesliga"]
    assert out["name"].iloc[0] == "Marco Grüll" and out.attrs["date"] == "2027-09-05"
    assert rollen_attr.ziel_stufe(out.assign(eigen="kader", team="Senior Team"), LG) == "Exzellent"
