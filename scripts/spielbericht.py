"""Ergebnisbildschirm aus dem F9-Export des SpielLoggers lesen -> Daten im YAML-Format von spiel_erfassen.py.

Zugeordnet wird über die Elementnamen der Spieloberfläche (z. B. .../Possession/bar/Left-frame), nicht über Texte
in einer Sprache. Fehlende Werte werden benannt, nicht geschätzt.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Elementname im Spiel -> Schlüssel in spiel_erfassen.WERTE
STATS = {
    "Possession": "ballbesitz", "Shots": "schuesse", "ShotsOnTarget": "schuesse_aufs_tor", "xG": "xg",
    "OPPDA": "ppda", "ClearCutChances": "grosschancen", "Corners": "ecken", "ProgressivePasses": "prog_paesse",
    "PassesCompleted": "passquote", "CrossesCompleted": "flankenquote", "Fouls": "fouls", "YellowCards": "gelb",
    "RedCards": "rot", "DistanceCovered": "laufleistung", "AvgRating": "notenschnitt",
}  # fmt: skip
SLOTS = {
    "GK": "TW", "DL": "LV", "DCL": "IV l", "DCR": "IV r", "DR": "RV", "DML": "DM l", "DMR": "DM r", "DMC": "DM",
    "AML": "OM l", "AMC": "OM z", "AMR": "OM r", "ST": "ST",
}  # fmt: skip
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")  # fmt: skip
DATUM = re.compile(rf"(\d{{1,2}})\. ({'|'.join(MONATE)}) (\d{{4}})")


def _sauber(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("\xa0", " ").strip()


def lesen(pfad: Path) -> dict | None:
    """-> {datum, heim, gast, wettbewerb, werte: {key: [heim, gast]}, aufstellung: [[...heim], [...gast]]}
    oder None, wenn der Export kein Ergebnisbildschirm ist."""
    d = json.loads(Path(pfad).read_text(encoding="utf-8-sig"))
    texte = [{**t, "text": _sauber(t["text"])} for t in d.get("texte", [])]
    werte: dict[str, list] = {}
    bericht: dict = {"datum": None, "heim": None, "gast": None, "wettbewerb": None, "datei": Path(pfad).name}
    for t in texte:
        pfad_t = t.get("pfad", [])
        if "bar" in pfad_t[1:]:
            key = STATS.get(pfad_t[pfad_t.index("bar", 1) - 1])
            seite = 0 if "Left-frame" in pfad_t else 1 if "Right-frame" in pfad_t else None
            if key and seite is not None:
                werte.setdefault(key, [None, None])[seite] = t["text"].replace("%", "").strip()
        if "ClubName" in pfad_t:
            if "HomeTeam" in pfad_t:
                bericht["heim"] = t["text"]
            elif "AwayTeam" in pfad_t:
                bericht["gast"] = t["text"]
        if any("MatchResult" in p for p in pfad_t):
            if m := DATUM.search(t["text"]):
                bericht["datum"] = f"{m[3]}-{MONATE.index(m[2]) + 1:02d}-{int(m[1]):02d}"
            if m := re.fullmatch(r"(\d+) - (\d+)", t["text"]):
                werte["tore"] = [m[1], m[2]]
            if pfad_t[-1] == "ClubText" or "ClubText" in pfad_t[-3:]:
                bericht["wettbewerb"] = bericht["wettbewerb"] or t["text"]
    if len(werte) < 5 or not bericht["heim"] or not bericht["gast"]:
        return None
    bericht["werte"] = werte
    bericht["aufstellung"] = _aufstellung(texte)
    return bericht


def _aufstellung(texte: list[dict]) -> list[list[dict]]:
    """Beide Formationskacheln (links Heim, rechts Gast): Name, Slot, Rolle, Note."""
    namen = [t for t in texte if len(p := t.get("pfad", [])) >= 3 and p[-3] in SLOTS and p[-2:] == ["Player", "Name"]]
    if not namen:
        return [[], []]
    mitte = (min(t["x"] for t in namen) + max(t["x"] for t in namen)) / 2

    def darueber(n, element):
        treffer = [
            t for t in texte
            if t.get("pfad", [""])[-1] == element and abs(t["x"] - n["x"]) < 60 and 0 < n["y"] - t["y"] < 35
        ]  # fmt: skip
        return min(treffer, key=lambda t: abs(t["x"] - n["x"]))["text"] if treffer else None

    ergebnis: list[list[dict]] = [[], []]
    for n in namen:
        ergebnis[int(n["x"] > mitte)].append({
            "slot": SLOTS[n["pfad"][-3]], "spieler": n["text"],
            "rolle": darueber(n, "PositionContainer"), "note": darueber(n, "Rating"),
        })  # fmt: skip
    return ergebnis


def alle(ordner: Path) -> list[dict]:
    """Alle Ergebnisbildschirme im Ordner, neueste zuletzt."""
    return [b for f in sorted(ordner.glob("*.json")) if (b := lesen(f))]
