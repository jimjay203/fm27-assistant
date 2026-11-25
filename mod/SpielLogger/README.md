# SpielLogger (Test)

BepInEx-6-Plugin: schreibt während eines Spiels Ereignisse, Spieler- und Ballpositionen als JSONL nach
`BepInEx\SpielLogger\`. Zweck: prüfen, ob sich ein Import in `db/fm27.sqlite` lohnt.

- Nur lesend, keine Harmony-Haken, keine Anzeige im Spiel. Die Datei kann Ereignisse enthalten, die im Spiel noch
  nicht gezeigt wurden – während des Spiels nicht hineinschauen, wenn das stört.
- Vor dem ersten Test den Spielstand sichern; fällt etwas auf, nicht speichern.

Bauen und installieren: `dotnet build -c Release -p:Installieren=true` (wirkt nach Neustart von FM27).
Entfernen: Ordner `BepInEx\plugins\SpielLogger` löschen.

## Stufen (`BepInEx\config\fm27assistant.spiellogger.cfg`, im Spiel F7)

| Stufe | Inhalt |
|---|---|
| 0 | aus |
| 1 | Zähler: Anzahl Ereignisse, Zeitscheibe |
| 2 | + Spielerliste, Ereignisfelder |
| 3 | + Positionen (bis 30 Hz, `PositionenHz`) |
| 4 (Standard) | + Ball je Zeitscheibe, nur nach F8 und solange das Spiel steht (Halbzeit, Abpfiff) |

## Bedienung

| Wann | Taste |
|---|---|
| Halbzeit | F8 (Stand schreiben) |
| Abpfiff | F8 |
| Ergebnis-, Statistik-, Taktik- oder andere Ansicht festhalten | F9 → `BepInEx\SpielLogger\bildschirm\*.json` |

Ruckelt etwas: Die Zeile `leistung` im Mitschnitt nennt die längste Dauer je Aufgabe, Bilder über 100 ms (`ruckler`)
und wie viele davon mit eigener Arbeit zusammenfielen (`ruckler_eigen`). F7 bis Stufe 0 schaltet den Mitschnitt aus.

## Auswertung

| Befehl (`uv run python …`) | Inhalt |
|---|---|
| `scripts/spielimport.py` | Archiv, DB, Spielbericht aus dem F9-Export |
| `scripts/spielanalyse.py tore` / `szenen` | Torabläufe mit je zwei Grafiken, alle Abschlüsse |
| `scripts/spielanalyse.py team [--gegner]` / `spieler NAME` | Form, Ballwechsel, Passwege |
| `scripts/spielanalyse.py halbzeit` | Stand bis jetzt (nach F8) |
| `scripts/spiellog.py` | technischer Prüfbericht zum Mitschnitt |

Das Spiel rechnet Ereignisse voraus und ersetzt sie (z. B. nach Wechseln): je `i` gilt die letzte Zeile.

`uv run python scripts/spiellog.py <datei.jsonl>` (ohne Datei: neueste im Standardordner).
