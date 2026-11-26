"""Datenmodell eines SpielLogger-Mitschnitts: Ereignisse mit Kategorie, Spielzeit, Ball- und Spielerpositionen.

Grundsatz: Standardmäßig nur, was bereits gespielt/gesehen wurde (das Spiel rechnet Ereignisse voraus) – so ist
eine Halbzeit-Analyse ohne Blick in die Zukunft möglich. Koordinaten in Metern, Feldmitte = 0, quer x, Höhe y,
längs z. `lage(team, …)` dreht so, dass `team` nach +z angreift; dann ist +x dessen rechte Seite.
"""

from __future__ import annotations

import bisect
import datetime as dt
import re
import sqlite3
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import common
import spiellog

JE_SEKUNDE = 4  # Zeitscheiben je Spielsekunde
LOG_ORDNER = spiellog.FM27 / "BepInEx" / "SpielLogger"


@dataclass
class Spieler:
    uid: int
    team: int
    name: str
    nr: int
    index: int
    art: str


@dataclass
class Ereignis:
    i: int
    ts: int
    name: str  # ohne "Event"
    kat: str
    uids: list[int]  # nur Spieler des Spiels, Reihenfolge wie im Spiel
    seite: str  # "Home"/"Away" laut Spiel (bei Standards: wer ausführt)
    laenge: int  # data1: bei Pässen/Schüssen Entfernung in 5-m-Stufen
    text: str = ""


@dataclass
class Spiel:
    datei: Path
    kopf: dict
    setup: dict
    spieler: dict[int, Spieler]
    ereignisse: list[Ereignis]
    frames: list[dict]
    ball: dict[int, list[float]]
    bildschirme: list[str]
    gesehen: int
    unbekannt: Counter = field(default_factory=Counter)

    def __post_init__(self):
        self._frame_ts = [f["ts"] for f in self.frames]
        self._ball_ts = sorted(self.ball)
        self._index = {s.index: s for s in self.spieler.values()}
        self._richtung = self._richtungen()

    # ------------------------------------------------------------------ Zeit

    def _frame_nahe(self, ts: int) -> dict | None:
        if not self.frames:
            return None
        k = bisect.bisect_left(self._frame_ts, ts)
        kandidaten = [self.frames[j] for j in (k - 1, k) if 0 <= j < len(self.frames)]
        return min(kandidaten, key=lambda f: abs(f["ts"] - ts))

    def zeit(self, ts: int) -> tuple[str, int]:
        """(Periode, Sekunden auf der Spieluhr)."""
        f = self._frame_nahe(ts)
        if f is None:
            return "?", ts // JE_SEKUNDE
        return f["periode"], max(0, round(f["min"] * 60 + f["sek"] + (ts - f["ts"]) / JE_SEKUNDE))

    def uhr(self, ts: int) -> str:
        _, s = self.zeit(ts)
        return f"{s // 60}:{s % 60:02d}"

    def minute(self, ts: int) -> str:
        """Minute wie im Spielbericht: 5:59 -> 6', 45:19 in Halbzeit 1 -> 45+1'."""
        periode, s = self.zeit(ts)
        ende = {"FirstHalf": 45, "SecondHalf": 90}.get(periode)
        m = s // 60 + 1
        return f"{ende}+{m - ende}'" if ende and m > ende else f"{m}'"

    # ------------------------------------------------------------------ Richtung und Positionen

    def torwart(self, team: int) -> set[int]:
        """Index des Torwarts: der erste Feldspieler-Eintrag je Team (Startelf beginnt mit dem Torwart)."""
        feld = sorted(s.index for s in self.spieler.values() if s.team == team and s.art == "Player")
        return set(feld[:1])

    def _richtungen(self) -> dict[tuple[str, int], int]:
        """+1, wenn das Team in dieser Periode nach +z angreift (Torwart steht bei -z)."""
        werte: dict[tuple[str, int], list[float]] = {}
        torwarte = {i: t for t in (0, 1) for i in self.torwart(t)}
        for f in self.frames[::5]:
            for p in f.get("spieler", []):
                team = torwarte.get(int(p[0]))
                if team is not None and abs(p[1]) < 36:  # nicht auf der Bank
                    werte.setdefault((f["periode"], team), []).append(p[3])
        return {k: (1 if statistics.median(v) < 0 else -1) for k, v in werte.items()}

    def richtung(self, team: int, ts: int) -> int:
        return self._richtung.get((self.zeit(ts)[0], team), 1)

    def lage(self, team: int, ts: int, pos: list[float]) -> tuple[float, float]:
        """(quer, längs) so gedreht, dass `team` nach oben angreift."""
        r = self.richtung(team, ts)
        return pos[0] * r, pos[2] * r

    def ball_bei(self, ts: int, toleranz: int = 4) -> list[float] | None:
        """Ball zur Zeitscheibe ts: gemessen, zwischen zwei nahen Messungen interpoliert oder die nächste."""
        if ts in self.ball:
            return self.ball[ts]
        k = bisect.bisect_left(self._ball_ts, ts)
        if 0 < k < len(self._ball_ts):
            a, b = self._ball_ts[k - 1], self._ball_ts[k]
            if b - a <= 2 * toleranz:
                anteil = (ts - a) / (b - a)
                return [x + (y - x) * anteil for x, y in zip(self.ball[a], self.ball[b], strict=True)]
        kandidaten = [self._ball_ts[j] for j in (k - 1, k) if 0 <= j < len(self._ball_ts)]
        if not kandidaten:
            return None
        n = min(kandidaten, key=lambda t: abs(t - ts))
        return self.ball[n] if abs(n - ts) <= toleranz else None

    def positionen(self, ts: int, toleranz: int = 6) -> dict[int, list[float]]:
        """uid -> [x, y, z] aller Spieler auf dem Feld, zwischen zwei Messungen interpoliert; {} = keine Messung."""
        k = bisect.bisect_left(self._frame_ts, ts)
        davor = self.frames[k - 1] if k > 0 else None
        danach = self.frames[k] if k < len(self.frames) else None
        if danach and danach["ts"] == ts:
            davor = danach
        if davor and danach and 0 <= danach["ts"] - davor["ts"] <= 2 * toleranz:
            anteil = (ts - davor["ts"]) / (danach["ts"] - davor["ts"]) if danach["ts"] != davor["ts"] else 0.0
        else:
            f = self._frame_nahe(ts)
            if f is None or abs(f["ts"] - ts) > toleranz:
                return {}
            davor, danach, anteil = f, f, 0.0
        b = {int(p[0]): p[1:] for p in danach["spieler"]}
        ergebnis = {}
        for p in davor["spieler"]:
            s = self._index.get(int(p[0]))
            if s is None or s.art != "Player" or abs(p[1]) >= 36:
                continue
            ende = b.get(s.index, p[1:])
            ergebnis[s.uid] = [a + (e - a) * anteil for a, e in zip(p[1:], ende, strict=False)]
        return ergebnis

    # ------------------------------------------------------------------ Teams

    def name(self, uid: int) -> str:
        s = self.spieler.get(uid)
        return s.name if s else str(uid)

    def team(self, uid: int) -> int | None:
        s = self.spieler.get(uid)
        return s.team if s else None

    def team_von(self, e: Ereignis) -> int | None:
        """Team des handelnden Spielers; ohne Spieler die Seite laut Spiel (Home = Team 0)."""
        if e.uids:
            return self.team(e.uids[0])
        return {"Home": 0, "Away": 1}.get(e.seite)


def kategorien(config_dir=None) -> list[tuple[str, re.Pattern]]:
    roh = common.load_yaml("spiel_ereignisse.yaml", config_dir)["kategorien"]
    return [(k, re.compile("|".join(muster))) for k, muster in roh.items()]


def kategorie(name: str, regeln: list[tuple[str, re.Pattern]]) -> str:
    return next((k for k, r in regeln if r.search(name)), "sonstiges")


def laden(pfad: Path, alles: bool = False, config_dir=None) -> Spiel:
    d = spiellog.lesen(pfad)
    spieler = {
        s["uid"]: Spieler(s["uid"], s["team"], s.get("name") or str(s["uid"]), s.get("nr", 0), s["index"], s["art"])
        for s in d.get("spieler", [])
        if s.get("uid", -1) > 0
    }
    # Live-Messungen vor Wiederholungen: je Zeitscheibe die erste Messung
    je_ts: dict[int, dict] = {}
    for f in sorted(d.get("frame", []), key=lambda f: str(f.get("modus", "")).startswith("Replay")):
        if f.get("aktiv"):
            je_ts.setdefault(f["ts"], f)
    frames = [je_ts[t] for t in sorted(je_ts)]
    gesehen = max(
        [z.get("gesehen", z.get("ts", 0)) for z in d.get("zaehler", [])] + [f["ts"] for f in frames] + [0]
    )
    ball = {ts: f["ball"] for ts, f in je_ts.items() if f.get("ball")}
    ball.update({r["ts"]: r["ball"] for r in spiellog.ball_rueck(d)})
    regeln = kategorien(config_dir)
    ereignisse, unbekannt = [], Counter()
    for e in spiellog.endstand(d):
        if not alles and e["ts"] > gesehen:
            continue
        name = e["name"].removeprefix("Event")
        kat = kategorie(name, regeln)
        if kat == "sonstiges":
            unbekannt[name] += 1
        ereignisse.append(Ereignis(
            e.get("i", len(ereignisse)), e["ts"], name, kat, [u for u in e.get("spieler", []) if u in spieler],
            e.get("team", ""), e.get("data1", 0), (e.get("text") or [""])[0],
        ))  # fmt: skip
    ereignisse.sort(key=lambda e: (e.ts, e.i))
    if not alles:
        ball = {t: p for t, p in ball.items() if t <= gesehen}
    return Spiel(
        pfad, (d.get("kopf") or [{}])[0], (d.get("setup") or [{}])[0], spieler, ereignisse, frames, ball,
        [b["datei"] for b in d.get("bildschirm", [])], gesehen, unbekannt,
    )  # fmt: skip


def neuester(ordner: Path = LOG_ORDNER) -> Path:
    """Der Mitschnitt mit den meisten Messungen unter den Dateien des zuletzt aufgenommenen Spiels."""
    dateien = sorted(ordner.glob("*.jsonl"))
    if not dateien:
        raise FileNotFoundError(f"Kein Mitschnitt in {ordner}")
    spiel_id = dateien[-1].stem.rsplit("_", 1)[-1]
    if spiel_id == "0":  # keine Kennung: jede Datei ist ein eigenes Spiel
        return dateien[-1]
    gleiche = [d for d in dateien if d.stem.rsplit("_", 1)[-1] == spiel_id]
    return max(gleiche, key=lambda d: d.stat().st_size)


def unser_team(spiel: Spiel, conn: sqlite3.Connection, save: str) -> int:
    """Team (0 = Heim, 1 = Gast), dessen Spieler im neuesten Kader-Export stehen."""
    kader = {
        int(r[0])
        for r in conn.execute(
            "SELECT player_uid FROM players WHERE snapshot_id=(SELECT id FROM snapshots WHERE save=? "
            "AND view_type='kader' ORDER BY ingame_date DESC, id DESC LIMIT 1)",
            (save,),
        )
    }
    treffer = Counter(s.team for s in spiel.spieler.values() if s.art == "Player" and s.uid in kader)
    if not treffer:
        raise ValueError("Eigenes Team nicht erkennbar: kein Spieler des Mitschnitts steht im Kader-Export.")
    return treffer.most_common(1)[0][0]


def datum_aus_setup(setup: dict) -> str | None:
    """In-Game-Datum aus Jahr (Kalenderjahr des Spiels, auch im Januar) und Tag im Jahr (Plugin ab 0.2)."""
    try:
        jahr = int(setup["info"]["competitionYear"])
        tag = int(setup["wetter"]["day"])
    except (KeyError, TypeError, ValueError):
        return None
    if jahr <= 0 or tag <= 0:  # im laufenden Spiel liefert das Setup teils nur Nullen
        return None
    return (dt.date(jahr, 1, 1) + dt.timedelta(days=tag - 1)).isoformat()


def gegner_aus_db(spiel: Spiel, conn: sqlite3.Connection, wir: int) -> str | None:
    """Häufigster Verein der gegnerischen Spieler im neuesten Export, der sie enthält."""
    vereine = Counter()
    for s in spiel.spieler.values():
        if s.art != "Player" or s.team == wir:
            continue
        r = conn.execute(
            "SELECT p.club FROM players p JOIN snapshots n ON n.id=p.snapshot_id WHERE p.player_uid=? "
            "AND p.club IS NOT NULL ORDER BY n.ingame_date DESC, n.id DESC LIMIT 1",
            (str(s.uid),),
        ).fetchone()
        if r:
            vereine[r[0]] += 1
    return vereine.most_common(1)[0][0] if vereine else None

