"""Kaderplaner als lokale Web-App: Formation und Rollen wählen, beste eigene Spieler und Verbesserungen sehen.

Fachlogik: scripts/planer.py (Rollen-Score aus scripts/rollen.py). Oberfläche: web/. Der Server bindet nur an
127.0.0.1 und schreibt nichts in die DB außer der Schema-Migration von common.connect().

Spielerbilder: face_<uid>.png aus dem FM27-Faces-Ordner (--faces, sonst $FM27_FACES, sonst der Standardpfad unter
Dokumente). Fehlt ein Bild, zeigt die Oberfläche die Initialen.

FMMT-27-Reader: wird mitgestartet, wenn er nicht läuft (scripts/fmmt.py; --fmmt DIR, sonst $FM27_FMMT, sonst
~/Developer/fmmt-27-fork; --kein-fmmt schaltet das ab). Quelle "auto" (Standard): live, wenn FM27 läuft und lesbar ist,
sonst DB. Scheitert die Live-Ladung beim Start, läuft der Planer mit der DB weiter.

Aufruf:  uv run python scripts/webapp.py --save werder [--quelle auto|live|db] [--port 8700] [--kein-browser]
         [--faces DIR] [--fmmt DIR | --kein-fmmt]
"""

from __future__ import annotations

import argparse
import atexit
import os
import re
import sys
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import fmmt
import live
import planer
import spiele
import spielerprofil

WEB = common.ROOT / "web"
FACES_STANDARD = (
    Path.home() / "Documents" / "Sports Interactive" / "Football Manager 27" / "graphics" / "faces"
)
UID = re.compile(r"^\d{1,12}$")


def faces_ordner(arg: str | None = None) -> Path | None:
    """Faces-Ordner: Argument, sonst $FM27_FACES, sonst der FM27-Standardpfad; None, wenn er nicht existiert."""
    pfad = Path(arg or os.environ.get("FM27_FACES") or FACES_STANDARD)
    return pfad if pfad.is_dir() else None


class FilterIn(BaseModel):
    min_minuten: int = 900
    min_minuten_eigene: int = 400
    max_alter: int | None = None
    max_wert_mio: float | None = None
    min_stufe: str | None = None
    gewichtung: str | None = None
    nur_volle_daten: bool = False
    nur_suche: bool = True
    top_eigene: int = 8
    top_kandidaten: int = 15


class PlanIn(BaseModel):
    formation: str
    slots: dict[str, dict[str, str]] = {}
    filter: FilterIn = FilterIn()
    aufstellung: str = "einsaetze"  # "einsaetze" (wie bisher gespielt, Standard) oder "score"


class SucheIn(BaseModel):
    """Spielersuche: Rollenpaar plus Kriterien (siehe planer.Suche)."""

    mit: str
    ohne: str
    text: str = ""
    min_alter: int | None = None
    max_alter: int | None = None
    max_wert_mio: float | None = None
    min_stufe: str | None = None
    gewichtung: str | None = None
    min_minuten: int = 900
    nur_volle_daten: bool = False
    nur_suche: bool = False
    eigene: bool = True
    key_max_fehlt: int | None = Field(None, ge=0)
    limit: int = Field(150, ge=1, le=1000)


class ReloadIn(BaseModel):
    """Nur gesetzte Felder ändern die Einstellungen, der Rest bleibt wie zuletzt geladen."""

    quelle: str | None = None
    pool_min_stufe: str | None = None
    anker_min_n: int | None = None


def _fehler(e: SystemExit, status: int = 400) -> HTTPException:
    text = getattr(e, "meldung", None) or (e.code if isinstance(e.code, str) else None)
    return HTTPException(status_code=status, detail=text or "Fehler")


def create_app(
    laden: Callable[[dict], planer.Kontext], start: dict, faces: Path | None = None,
    erfassen: Callable[[bool], dict] | None = None,
) -> FastAPI:  # fmt: skip
    """`laden(einstellungen) -> Kontext`; `start` = Einstellungen der ersten Ladung (quelle, pool_min_stufe, ...).

    `faces`: Ordner mit face_<uid>.png (None = keine Bilder, die Oberfläche zeigt Initialen).
    `erfassen(schnell) -> Ergebnis`: Spiellisten aus FM27 lesen und speichern (scripts/spiele.py); None = aus."""
    app = FastAPI(title="FM27 Kaderplaner")
    state = {"ctx": laden(start), "einstellungen": dict(start)}
    lock = threading.Lock()

    @app.get("/api/meta")
    def meta():
        ctx = state["ctx"]
        return {
            "formationen": planer.formationen_meta(ctx),
            "standard": ctx.formationen.get("standard"),
            "stand": ctx.stand,
            "einstellungen": state["einstellungen"],
            "luecken": ctx.luecken,
            "stufen": ctx.lg.stufen,
            "gewichtungen": ["aus", *ctx.lg.schemata()],
            "filter_standard": asdict(planer.Filter()),
            "einsaetze": einsatz_stand(ctx),
            "erfassen_moeglich": erfassen is not None,
        }

    def einsatz_stand(ctx) -> dict | None:
        if not ctx.db:
            return None
        conn = common.connect(ctx.db_path)
        try:
            return spiele.stand(conn, ctx.save)
        finally:
            conn.close()

    erfass_lock = threading.Lock()

    @app.post("/api/spiele/erfassen")
    def spiele_erfassen(schnell: bool = False):
        if erfassen is None:
            raise HTTPException(status_code=400, detail="Erfassen ist nicht eingerichtet.")
        if not erfass_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Eine Erfassung läuft bereits.")
        try:
            res = erfassen(schnell)
        except SystemExit as e:
            raise _fehler(e, 503) from None
        finally:
            erfass_lock.release()
        return {**res, "stand": einsatz_stand(state["ctx"])}

    @app.post("/api/plan")
    def plan(body: PlanIn):
        f = planer.Filter(**{k.name: getattr(body.filter, k.name) for k in fields(planer.Filter)})
        try:
            return planer.plan(state["ctx"], body.formation, body.slots, f, body.aufstellung)
        except SystemExit as e:
            raise _fehler(e) from None

    @app.post("/api/suche")
    def suche(body: SucheIn):
        kriterien = planer.Suche(**body.model_dump(exclude={"mit", "ohne"}))
        try:
            return planer.suche(state["ctx"], body.mit, body.ohne, kriterien)
        except SystemExit as e:
            raise _fehler(e) from None

    @app.get("/api/spieler/{uid}")
    def spieler(
        uid: str, mit: str, ohne: str, vergleich: str | None = None, gewichtung: str | None = None
    ):
        try:
            return spielerprofil.profil(state["ctx"], uid, mit, ohne, vergleich, gewichtung or None)
        except SystemExit as e:
            raise _fehler(e, 404 if "nicht in den geladenen Daten" in str(e) else 400) from None

    @app.get("/api/face/{uid}")
    def face(uid: str):
        # nur Ziffern: kein Pfad außerhalb des Faces-Ordners erreichbar
        datei = faces / f"face_{uid}.png" if faces and UID.match(uid) else None
        if not datei or not datei.is_file():
            raise HTTPException(status_code=404, detail="kein Bild")
        return FileResponse(
            datei, media_type="image/png", headers={"Cache-Control": "max-age=86400"}
        )

    @app.post("/api/reload")
    def reload(body: ReloadIn):
        neu = {**state["einstellungen"], **body.model_dump(exclude_none=True)}
        with lock:
            try:
                ctx = laden(neu)
            except SystemExit as e:  # z. B. FMMT nicht erreichbar: alter Kontext bleibt aktiv
                raise _fehler(e, 503) from None
            state["ctx"], state["einstellungen"] = ctx, neu
        return {"stand": ctx.stand, "einstellungen": neu}

    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

        @app.get("/")
        def index():
            return FileResponse(WEB / "index.html")

    return app


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument(
        "--quelle", choices=["auto", "db", "live"], default="auto",
        help="auto (Default): live, wenn FM27 lesbar ist, sonst DB",
    )  # fmt: skip
    ap.add_argument(
        "--verein", help="Eigener Verein (Default: häufigster Verein im Kader-Snapshot)"
    )
    ap.add_argument("--url", default=live.DEFAULT_URL, help="FMMT-27-Server für --quelle live")
    ap.add_argument("--pool-min-stufe", default="Gut", help="Vergleichspool der Anker")
    ap.add_argument(
        "--anker-min-n", type=int, default=100, help="Mindestwerte je Statistik im Pool"
    )
    ap.add_argument("--port", type=int, default=8700)
    ap.add_argument("--kein-browser", action="store_true")
    ap.add_argument(
        "--faces", help=f"Ordner mit face_<uid>.png (Default: $FM27_FACES oder {FACES_STANDARD})"
    )
    ap.add_argument(
        "--fmmt", help=f"FMMT-27-Ordner (Default: $FM27_FMMT oder {fmmt.FMMT_STANDARD})"
    )
    ap.add_argument("--kein-fmmt", action="store_true", help="FMMT-27-Reader nicht mitstarten")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)

    reader = None
    if not a.kein_fmmt:
        reader = fmmt.Reader(a.url, fmmt.ordner(a.fmmt))
        atexit.register(reader.stoppen)
        ergebnis = reader.sicherstellen()
        print(
            f"FMMT-27-Reader: {ergebnis}" + (" (FM27 lesbar)" if fmmt.spiel_bereit(a.url) else "")
        )

    def laden(e: dict) -> planer.Kontext:
        if e["quelle"] == "live" and reader:
            reader.sicherstellen()  # z. B. nach "Neu laden: live", falls der Reader inzwischen beendet wurde
        return planer.kontext_laden(
            save, e["quelle"], a.verein, a.url, a.db, a.config_dir,
            pool_min_stufe=e["pool_min_stufe"], anker_min_n=e["anker_min_n"],
        )  # fmt: skip

    def erfassen(schnell: bool) -> dict:
        if reader:
            reader.sicherstellen()
        antwort = spiele.abrufen(a.url, schnell)
        conn = common.connect(a.db)
        try:
            res = spiele.erfassen(conn, save, antwort["lists"])
        finally:
            conn.close()
        return {**res, "modus": antwort.get("mode"), "sekunden": antwort.get("seconds")}

    quelle = a.quelle
    if quelle == "auto":
        quelle = "live" if fmmt.spiel_bereit(a.url) else "db"
    start = {"quelle": quelle, "pool_min_stufe": a.pool_min_stufe, "anker_min_n": a.anker_min_n}
    faces = faces_ordner(a.faces)
    if faces is None:
        print("Hinweis: kein Faces-Ordner gefunden, Spielerbilder werden durch Initialen ersetzt.")
    try:
        app = create_app(laden, start, faces, erfassen)
    except SystemExit as e:
        if quelle != "live" or a.quelle == "live":
            raise
        print(f"Live-Daten nicht ladbar ({getattr(e, 'meldung', e)}), weiter mit der DB.")
        start["quelle"] = "db"
        app = create_app(laden, start, faces, erfassen)
    print(f"Quelle: {start['quelle']}")

    import uvicorn

    url = f"http://127.0.0.1:{a.port}/"
    print(f"Kaderplaner ({save}) unter {url}")
    if not a.kein_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
