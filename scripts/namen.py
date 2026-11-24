"""Spielernamen abgleichen: Live-Namen (FMMT-27, Speicher) gegen die Namen der Exporte und taktik.md.

Der Speicher liefert für manche Spieler einen anderen Namen als das Spiel anzeigt (Lizenz-/Ersatzname, z. B.
"Marco Benke" statt "Marco Grüll"). Maßgeblich ist die player_uid: live und Export teilen sie. Reihenfolge:
  1. config/namen_alias.yaml, Abschnitt `uid` (uid -> Anzeigename), für Spieler ohne Export
  2. Name im neuesten Export (Kader vor Suche) mit derselben uid
  3. config/namen_alias.yaml, Abschnitt `name` (Live-Name -> Anzeigename), nur wenn keine uid passt
Der Live-Name bleibt in der Spalte `name_live` erhalten.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def name_norm(s) -> str:
    """Name ohne Akzente und Groß-/Kleinschreibung ('Dinkçi' -> 'dinkci')."""
    s = unicodedata.normalize("NFKD", s if isinstance(s, str) else "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def passt(name, eintrag) -> bool:
    """Ganzer Name oder Nachname ('Grüll' passt zu 'Marco Grüll', 'Arthur' zu 'Arthur')."""
    n, e = name_norm(name), name_norm(eintrag)
    return bool(n) and bool(e) and (n == e or n.split()[-1] == e)


def alias_laden(config_dir: Path | None = None) -> dict:
    """{"uid": {uid: name}, "name": {norm(live-name): name}} aus config/namen_alias.yaml."""
    cfg = common.load_yaml("namen_alias.yaml", config_dir)
    return {
        "uid": {str(k): str(v) for k, v in (cfg.get("uid") or {}).items()},
        "name": {name_norm(k): str(v) for k, v in (cfg.get("name") or {}).items()},
    }


def export_namen(conn, save: str, views=("suche", "kader")) -> dict[str, str]:
    """uid -> Name im neuesten Export; bei gleichem Datum gewinnt der Kader."""
    rows = conn.execute(
        "SELECT p.player_uid, p.name FROM players p JOIN snapshots s ON s.id = p.snapshot_id "
        f"WHERE s.save = ? AND s.view_type IN ({','.join('?' * len(views))}) AND p.name IS NOT NULL "
        "ORDER BY s.ingame_date, s.view_type = 'kader', s.id",
        (save, *views),
    ).fetchall()
    return {str(uid): name for uid, name in rows}  # späterer Snapshot überschreibt früheren


def anzeige_quelle(uid, live_name, export: dict, alias: dict) -> tuple[str, str | None]:
    """(Anzeigename, Quelle) eines Live-Spielers; Quelle None = Live-Name unverändert."""
    uid = str(uid)
    if uid in alias["uid"]:
        return alias["uid"][uid], "alias_uid"
    if uid in export:
        return export[uid], "export"
    if name_norm(live_name) in alias["name"]:
        return alias["name"][name_norm(live_name)], "alias_name"
    return live_name, None


def anzeige_name(uid, live_name, export: dict, alias: dict) -> str:
    return anzeige_quelle(uid, live_name, export, alias)[0]


def angleichen(df: pd.DataFrame, export: dict[str, str], alias: dict | None = None) -> pd.DataFrame:
    """Namen der Live-Tabelle auf die Anzeige-/Exportnamen setzen (siehe Modulkopf); `name_live` = Live-Name.
    attrs["namen_abweichend"]: [{uid, live, name, quelle, own}] aller geänderten Zeilen."""
    if df.empty or "name" not in df or "uid" not in df:
        return df
    alias = alias or {"uid": {}, "name": {}}
    df = df.copy()
    df["name_live"] = df["name"]
    neu, quelle = zip(
        *(
            anzeige_quelle(u, n, export, alias)
            for u, n in zip(df["uid"].astype(str), df["name"], strict=True)
        ),
        strict=True,
    )
    neu = list(neu)
    df["name"] = neu
    own = df["own"].fillna(False).astype(bool) if "own" in df else pd.Series(False, index=df.index)
    diff = df["name"].map(name_norm) != df["name_live"].map(name_norm)
    df.attrs["namen_abweichend"] = [
        {"uid": u, "live": lv, "name": n, "quelle": q, "own": bool(o)}
        for u, lv, n, q, o, d in zip(df["uid"].astype(str), df["name_live"], df["name"], quelle, own, diff,
                                     strict=True)
        if d
    ]  # fmt: skip
    return df


def uid_fuer_name(conn, save: str, name: str, views=("kader",)) -> list[tuple[str, str, str]]:
    """Eigene Spieler zu einem Namen (ganzer Name oder Nachname, ohne Akzente): [(uid, Name, Snapshot-Datum)].

    Gesucht wird im neuesten Kader-Export, der den Namen enthält (auch ältere, z. B. für inzwischen abgegebene
    Spieler). Mehrere Treffer im selben Export = mehrdeutig (Aufrufer entscheidet)."""
    snaps = conn.execute(
        f"SELECT id, ingame_date FROM snapshots WHERE save=? AND view_type IN ({','.join('?' * len(views))}) "
        "ORDER BY ingame_date DESC, id DESC",
        (save, *views),
    ).fetchall()
    for sid, datum in snaps:
        treffer = [
            (str(u), n, datum)
            for u, n in conn.execute(
                "SELECT player_uid, name FROM players WHERE snapshot_id=?", (sid,)
            )
            if passt(n, name)
        ]
        if treffer:
            exakt = [t for t in treffer if name_norm(t[1]) == name_norm(name)]
            return exakt or treffer
    return []
