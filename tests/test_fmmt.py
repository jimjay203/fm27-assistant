"""FMMT-27-Reader mitstarten: Ordner finden, fremden Reader in Ruhe lassen, eigenen starten und stoppen."""

import socket
import textwrap

import fmmt
import pytest

FAKE_SERVER = textwrap.dedent(
    """
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": False, "error": "game not running"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass

    assert "--no-browser" in sys.argv
    port = int(sys.argv[sys.argv.index("--port") + 1])
    HTTPServer(("127.0.0.1", port), H).serve_forever()
    """
)


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def fake_fmmt(tmp_path):
    (tmp_path / "reader").mkdir()
    (tmp_path / "reader" / "server.py").write_text(FAKE_SERVER, encoding="utf-8")
    return tmp_path


def test_ordner_nur_mit_reader(tmp_path, fake_fmmt, monkeypatch):
    monkeypatch.delenv("FM27_FMMT", raising=False)
    assert fmmt.ordner(str(fake_fmmt)) == fake_fmmt
    assert fmmt.ordner(str(tmp_path / "gibtsnicht")) is None
    monkeypatch.setenv("FM27_FMMT", str(fake_fmmt))
    assert fmmt.ordner() == fake_fmmt


def test_nicht_erreichbar_ohne_ordner():
    url = f"http://127.0.0.1:{freier_port()}"
    assert fmmt.status(url) is None and not fmmt.spiel_bereit(url)
    assert fmmt.Reader(url, None).sicherstellen(warten=1) == "kein Ordner"


def test_startet_meldet_und_stoppt_den_eigenen_reader(fake_fmmt, tmp_path):
    url = f"http://127.0.0.1:{freier_port()}"
    r = fmmt.Reader(url, fake_fmmt, log=tmp_path / "logs" / "fmmt.log")
    try:
        assert r.sicherstellen(warten=15) == "gestartet"
        assert fmmt.status(url) == {"ok": False, "error": "game not running"}
        assert not fmmt.spiel_bereit(url)  # Reader da, Spiel nicht
        # ein zweiter Verwalter findet den laufenden Reader und startet nichts
        zweiter = fmmt.Reader(url, fake_fmmt, log=tmp_path / "x.log")
        assert zweiter.sicherstellen(warten=1) == "läuft" and zweiter.proc is None
        zweiter.stoppen()  # fremder Reader bleibt unberührt
        assert fmmt.status(url) is not None
    finally:
        r.stoppen()
    assert fmmt.status(url, timeout=1) is None
    assert (tmp_path / "logs" / "fmmt.log").is_file()


def test_fehlgeschlagener_start_wird_gemeldet(tmp_path):
    (tmp_path / "reader").mkdir()
    (tmp_path / "reader" / "server.py").write_text("raise SystemExit(3)", encoding="utf-8")
    r = fmmt.Reader(f"http://127.0.0.1:{freier_port()}", tmp_path, log=tmp_path / "f.log")
    assert r.sicherstellen(warten=10).startswith("Start fehlgeschlagen: Reader beendet mit Code 3")
