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
