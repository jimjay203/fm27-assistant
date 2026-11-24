"""Gemeinsame Helfer: Pfade, Config, Save-Auswahl, DB-Zugriff + Schema."""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAVE = "werder"
PLAYER_VIEWS = ("kader", "suche", "scouting", "live")  # live = scripts/live.py (FMMT-27, Speicher)
TEAM_VIEWS = ("team_stats", "spiel")
VIEW_TYPES = PLAYER_VIEWS + TEAM_VIEWS

# Interne Kernfelder (fest). `attr_<name>` = Attribut, alles andere = Stat (long format).
PLAYER_CORE = (
    "uid",
    "name",
    "birthdate",
    "club",
    "league",
    "club_country",  # "Ansässig in": Land des Vereins; macht gleichnamige Ligen eindeutig
    "position",
    "age",
    "wage",
    "value",
    "contract_end",
    "loan_end",  # Leihende: 2. "Endet"-Spalte (pandas "Endet.1", Suche) bzw. Ende von "Leihdauer"
    "loan_start",  # Beginn aus "Leihdauer" (Kader)
    "minutes",
    "team_possession",  # TODO(export): Ballbesitz des Teams (%), für Defensiv-Bereinigung
)
TEAM_CORE = (
    "datum",
    "opponent",
    "home_away",
    "tactic_slot",
    "xg_for",
    "xg_against",
    "goals_for",
    "goals_against",
    "possession",
    "shots_for",
    "shots_against",  # TODO(export)
    "competition",  # Text, z. B. "Bundesliga", "DFB-Pokal" (Spielbericht-Erfassung, Export-Spalte "Wettbewerb")
)
TEAM_TEXT = ("datum", "opponent", "home_away", "tactic_slot", "competition")

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY, save TEXT NOT NULL, ingame_date TEXT NOT NULL,
  source_file TEXT NOT NULL, view_type TEXT NOT NULL, imported_at TEXT NOT NULL,
  UNIQUE(save, source_file));
CREATE TABLE IF NOT EXISTS snapshot_files(  -- Teil-Dateien eines Snapshots (Mehrteil-Suche); source_file = 1. Teil
  snapshot_id INTEGER NOT NULL, source_file TEXT NOT NULL, rows INTEGER,
  PRIMARY KEY(snapshot_id, source_file));
CREATE TABLE IF NOT EXISTS players(
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id), player_uid TEXT NOT NULL,
  name TEXT, club TEXT, league TEXT, position TEXT, age INTEGER,
  wage REAL,            -- Jahresgehalt in Euro (beim Import aus Woche/Monat umgerechnet)
  value REAL,           -- Transferwert; bei Spannen der Mittelwert (Grenzen in value_min/value_max)
  contract_end TEXT, minutes INTEGER, birthdate TEXT, team_possession REAL,
  value_min REAL, value_max REAL, loan_end TEXT,
  wage_min REAL, wage_max REAL,   -- Jahresgehalt-Spanne bei nicht gescouteten Spielern
  club_country TEXT, loan_start TEXT,
  PRIMARY KEY(snapshot_id, player_uid));
CREATE TABLE IF NOT EXISTS player_info(     -- Text-/Datumsfelder (typ: text|date in spalten.yaml)
  snapshot_id INTEGER NOT NULL, player_uid TEXT NOT NULL, field TEXT NOT NULL, text TEXT,
  PRIMARY KEY(snapshot_id, player_uid, field));
CREATE TABLE IF NOT EXISTS player_stats(
  snapshot_id INTEGER NOT NULL, player_uid TEXT NOT NULL, stat TEXT NOT NULL, value REAL,
  PRIMARY KEY(snapshot_id, player_uid, stat));
CREATE TABLE IF NOT EXISTS player_attributes(
  snapshot_id INTEGER NOT NULL, player_uid TEXT NOT NULL, attribute TEXT NOT NULL,
  value REAL,           -- exakter Wert; bei Scouting-Spannen NULL (masked=1), Grenzen in lo/hi
  masked INTEGER NOT NULL DEFAULT 0, lo REAL, hi REAL,
  PRIMARY KEY(snapshot_id, player_uid, attribute));
CREATE TABLE IF NOT EXISTS player_raw(      -- unbekannte (nicht gemappte) Spalten, unverändert
  snapshot_id INTEGER NOT NULL, player_uid TEXT NOT NULL, column_name TEXT NOT NULL, raw_value TEXT,
  PRIMARY KEY(snapshot_id, player_uid, column_name));
CREATE TABLE IF NOT EXISTS unmapped_columns(
  snapshot_id INTEGER NOT NULL, column_name TEXT NOT NULL, PRIMARY KEY(snapshot_id, column_name));
CREATE TABLE IF NOT EXISTS team_matches(
  id INTEGER PRIMARY KEY, snapshot_id INTEGER, save TEXT NOT NULL, ingame_date TEXT NOT NULL,
  opponent TEXT NOT NULL, home_away TEXT, tactic_slot TEXT, xg_for REAL, xg_against REAL,
  goals_for REAL, goals_against REAL, possession REAL, shots_for REAL, shots_against REAL,
  competition TEXT,
  UNIQUE(save, ingame_date, opponent));
CREATE TABLE IF NOT EXISTS team_match_stats(
  match_id INTEGER NOT NULL REFERENCES team_matches(id), stat TEXT NOT NULL, value REAL,
  PRIMARY KEY(match_id, stat));
CREATE TABLE IF NOT EXISTS leagues(league TEXT PRIMARY KEY, reputation_or_strength REAL);
CREATE TABLE IF NOT EXISTS league_ranking(  -- config/ligen.yaml: rang = Listenposition (1 = oben)
  league TEXT NOT NULL, country TEXT NOT NULL, rang INTEGER NOT NULL, ansehen TEXT, pos INTEGER,
  PRIMARY KEY(league, country));
CREATE TABLE IF NOT EXISTS spieleinsaetze(  -- scripts/spiele.py: Spiellisten aus FM27 (FMMT /api/matchlists)
  save TEXT NOT NULL, player_uid TEXT NOT NULL, datum TEXT NOT NULL,
  gegner_id INTEGER, wettbewerb INTEGER, eingesetzt INTEGER NOT NULL,
  position_bits INTEGER, rolle_id INTEGER, minuten INTEGER, einwechslung INTEGER, auswechslung INTEGER,
  note REAL, tore INTEGER, vorlagen INTEGER, xg REAL,
  roh TEXT,             -- alle 0x37 Bytes als Hex: noch nicht zugeordnete Felder bleiben erhalten
  erfasst_am TEXT NOT NULL,
  PRIMARY KEY(save, player_uid, datum));
"""


def write_team_match(
    conn, sid: int | None, save: str, date: str, opponent: str, werte: dict, extra: dict
) -> int:
    """Ein Spiel in team_matches + team_match_stats schreiben; ein Spiel gleichen Datums und Gegners wird ersetzt.

    `werte`: Kernfelder aus TEAM_CORE (ohne datum/opponent; home_away, tactic_slot, competition als Text),
    `extra`: weitere Stats (Name wie in spalten.yaml, z. B. ppda_for) -> team_match_stats. None wird nicht
    geschrieben. -> id des Spiels."""
    conn.execute(
        "DELETE FROM team_match_stats WHERE match_id IN "
        "(SELECT id FROM team_matches WHERE save=? AND ingame_date=? AND opponent=?)",
        (save, date, opponent),
    )
    conn.execute(
        "DELETE FROM team_matches WHERE save=? AND ingame_date=? AND opponent=?", (save, date, opponent)
    )
    cols = [c for c in TEAM_CORE if c not in ("datum", "opponent")]
    cur = conn.execute(
        f"INSERT INTO team_matches(snapshot_id, save, ingame_date, opponent, {', '.join(cols)}) "
        f"VALUES(?,?,?,?,{','.join('?' * len(cols))})",
        (sid, save, date, opponent, *(werte.get(c) for c in cols)),
    )
    for stat, v in extra.items():
        if v is not None:
            conn.execute("INSERT INTO team_match_stats VALUES(?,?,?)", (cur.lastrowid, stat, v))
    return cur.lastrowid


def setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--save", help="Save-Name (Default: $FM27_SAVE, sonst CLAUDE.md, sonst werder)")
    p.add_argument("--db", type=Path, help="Pfad zur SQLite-DB (Default: db/fm27.sqlite)")
    p.add_argument("--config-dir", type=Path, help="Config-Ordner (Default: config/)")


def resolve_save(arg: str | None = None) -> str:
    if arg:
        return arg
    if os.environ.get("FM27_SAVE"):
        return os.environ["FM27_SAVE"]
    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        m = re.search(r"Aktiver Save:\s*saves/([^/\s]+)/", claude_md.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return DEFAULT_SAVE


def save_dir(save: str) -> Path:
    return ROOT / "saves" / save


def load_yaml(name: str, config_dir: Path | None = None) -> dict:
    path = (config_dir or ROOT / "config") / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# Spalten, die nach dem ersten Schema dazukamen (CREATE IF NOT EXISTS ergänzt sie nicht).
_ADDED_COLUMNS = {
    "players": {"wage_min": "REAL", "wage_max": "REAL", "club_country": "TEXT",
                "loan_start": "TEXT"},
    "player_attributes": {"lo": "REAL", "hi": "REAL"},
    "team_matches": {"competition": "TEXT"},
}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, cols in _ADDED_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.environ.get("FM27_DB") or ROOT / "db" / "fm27.sqlite")
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


class Abbruch(SystemExit):
    """SystemExit(1) mit der Meldung als Attribut (für Aufrufer wie die Web-App)."""

    def __init__(self, meldung: str):
        super().__init__(1)
        self.meldung = meldung

    def __str__(self) -> str:
        return self.meldung


def die(msg: str) -> None:
    print(f"FEHLER: {msg}", file=sys.stderr)
    raise Abbruch(msg)
