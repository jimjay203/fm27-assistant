"""Web-API des Kaderplaners mit synthetischem Kontext (kein DB- oder FMMT-Zugriff)."""

import common
import ligen
import planer
import pytest
import webapp
from conftest import MINI_FORMATIONEN, mini_df, mini_rk
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    def laden(e):
        if e["quelle"] == "live":
            common.die("FMMT-27 unter http://127.0.0.1:8627 nicht erreichbar")
        return planer.kontext_bauen(
            mini_df(), mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900}, MINI_FORMATIONEN,
            anker_min_n=e["anker_min_n"],
        )  # fmt: skip

    app = webapp.create_app(laden, {"quelle": "db", "pool_min_stufe": "Gut", "anker_min_n": 100})
    return TestClient(app)


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["standard"] == "2er"
    slot = m["formationen"]["2er"]["slots"]["ST r"]
    assert slot["optionen"]["mit"] == ["Mit", "Neuer Name"]
    assert slot["mit"] == "Mit" and slot["ohne"] == "Ohne"
    assert "aus" in m["gewichtungen"] and "Gut" in m["stufen"]
    assert m["einstellungen"]["quelle"] == "db"


def test_plan(client):
    r = client.post("/api/plan", json={"formation": "2er", "filter": {"max_alter": 25}})
    assert r.status_code == 200
    p = r.json()
    assert set(p["slots"]) == {"ST r", "ST l"}
    assert sorted(p["elf"].values()) == ["A", "B"]
    assert all(z["age"] <= 25 for s in p["slots"].values() for z in s["verbesserungen"])


def test_plan_fehler_wird_400(client):
    r = client.post("/api/plan", json={"formation": "2er", "slots": {"ST r": {"mit": "Ohne"}}})
    assert r.status_code == 400
    assert "passt nicht" in r.json()["detail"]


def test_reload_live_nicht_erreichbar_behaelt_kontext(client):
    r = client.post("/api/reload", json={"quelle": "live"})
    assert r.status_code == 503
    assert "nicht erreichbar" in r.json()["detail"]
    assert client.get("/api/meta").json()["einstellungen"]["quelle"] == "db"
    ok = client.post("/api/reload", json={"quelle": "db", "anker_min_n": 50})
    assert ok.status_code == 200 and ok.json()["einstellungen"]["anker_min_n"] == 50


def test_startseite(client):
    r = client.get("/")
    assert r.status_code == 200 and "Kaderplaner" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_spielerprofil_endpoint(client):
    p = client.post("/api/plan", json={"formation": "2er"}).json()
    s = p["slots"]["ST r"]
    uid = s["verbesserungen"][0]["uid"]
    params = {"mit": s["mit"], "ohne": s["ohne"], "vergleich": s["gesetzt"]}
    r = client.get(f"/api/spieler/{uid}", params=params)
    assert r.status_code == 200
    j = r.json()
    assert j["spieler"]["uid"] == uid and j["vergleich"]["uid"] == s["gesetzt"]
    assert {"rollen", "statistiken", "attribute", "pool"} <= set(j)
    nf = client.get("/api/spieler/xyz", params={"mit": "Mit", "ohne": "Ohne"})
    assert nf.status_code == 404


def test_spielerbild_nur_ziffern_und_vorhandene_dateien(tmp_path):
    (tmp_path / "face_123.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path.parent / "face_geheim.png").write_bytes(b"x")

    def laden(e):
        return planer.kontext_bauen(
            mini_df(), mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900}, MINI_FORMATIONEN
        )

    c = TestClient(
        webapp.create_app(
            laden, {"quelle": "db", "pool_min_stufe": "Gut", "anker_min_n": 100}, tmp_path
        )
    )
    r = c.get("/api/face/123")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert c.get("/api/face/999").status_code == 404  # fehlt -> Initialen in der Oberfläche
    assert c.get("/api/face/..%2Fface_geheim").status_code == 404  # kein Pfad außerhalb
    assert c.get("/api/face/abc").status_code == 404


def test_ohne_faces_ordner_immer_404(client):
    assert client.get("/api/face/123").status_code == 404


def test_plan_liefert_punkte_und_label(client):
    p = client.post("/api/plan", json={"formation": "2er"}).json()
    s = p["slots"]["ST r"]
    k = s["punkte"]["kandidaten"]
    assert k and {"uid", "name", "value", "paar_gew"} <= set(k[0])
    assert [z["paar_gew"] for z in k] == sorted((z["paar_gew"] for z in k), reverse=True)
    assert {z["uid"] for z in s["punkte"]["eigene"]} == {"A", "B"}
    m = client.get("/api/meta").json()
    assert m["formationen"]["2er"]["slots"]["ST r"]["label"] == "ST r"  # ohne label: Schlüssel


def test_spiele_erfassen_endpoint():
    aufrufe = []

    def laden(e):
        return planer.kontext_bauen(
            mini_df(), mini_rk(), ligen.Ligen.laden(), {"min_minuten": 900}, MINI_FORMATIONEN
        )

    def erfassen(schnell):
        aufrufe.append(schnell)
        return {
            "listen": 3,
            "gespeichert": [],
            "offen": [],
            "modus": "quick" if schnell else "full",
            "sekunden": 1,
        }

    start = {"quelle": "db", "pool_min_stufe": "Gut", "anker_min_n": 100}
    c = TestClient(webapp.create_app(laden, start, None, erfassen))
    assert c.get("/api/meta").json()["erfassen_moeglich"] is True
    r = c.post("/api/spiele/erfassen?schnell=true")
    assert r.status_code == 200 and r.json()["modus"] == "quick" and aufrufe == [True]
    ohne = TestClient(webapp.create_app(laden, start))
    assert ohne.post("/api/spiele/erfassen").status_code == 400
