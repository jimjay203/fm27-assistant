# FM27-Assistent

Claude Code als Assistent für Football Manager 27: Subagents (`taktik`, `entwicklung`, `scouting`,
`analyst`), SQLite-Snapshots der Spieldaten und Python-Skripte für Moneyball-Auswertungen.
Regeln und aktiver Save stehen in [CLAUDE.md](CLAUDE.md).

**Stand:** Exporte für Kader, Spielersuche und Spiele sind gemappt (`config/spalten.yaml`) und importiert.
Hauptquelle ist live das laufende FM27 über den FMMT-27-Reader (`scripts/live.py`); dazu Rollen-Score
(`scripts/rollen.py`), Benchmarks, Fair Value, Sell/Keep, Spiellisten je Spieler (`scripts/spiele.py`) und der
Kaderplaner (Web-App). Welche Quelle für welches Thema Pflicht ist: CLAUDE.md, „Quellen je Thema“.
Aktueller Datenstand: `uv run python scripts/stand.py`.

## Setup (nur uv)

```
uv sync
uv run pytest
```

## Workflow

| Anlass | Export | Agent-Reihenfolge |
|---|---|---|
| Immer zuerst | – | `stand.py` (Datenstand, Live ja/nein, offene Prüfungen in log.md) |
| Vor Transferfenster | Kader + Spielersuche (Zielpositionen), live | analyst → taktik (Bedarf bestätigen) → scouting |
| Monatlich | Kader inkl. Stats + Attribute, Spiellisten (`spiele.py`) | analyst → entwicklung |
| Nach 3–5 Spielen / Taktikänderung | Team-/Spielstatistiken, Spiellisten | analyst → taktik (Messkriterium aus log.md prüfen) |
| Vor wichtigem Spiel | Gegner-Analyse-Screen | taktik |

Exporte mit In-Game-Datum und View-Typ ablegen: `saves/werder/data/raw/2027-01-15_suche_stuermer.csv`
(`view_type`: `kader`, `suche`, `scouting`, `team_stats`, `spiel`). Screenshots (png/jpg) zuerst von
Claude in CSV überführen lassen – kein OCR im Skript.

## Befehle

```
uv run python scripts/import.py --save werder                  # alle Dateien in data/raw/
uv run python scripts/per90.py --rolle stuermer_abschluss      # Per-90 + Perzentile (--csv out.csv)
uv run python scripts/value.py --rolle stuermer_abschluss --max-alter 31 --top 20
uv run python scripts/team.py --ab 2027-02-01                  # Team-KPIs, Vorher/Nachher
uv run python scripts/stand.py                                 # Datenstand aller Quellen
uv run python scripts/live.py                                  # Live-Import aus FM27 (FMMT-27)
uv run python scripts/rollen.py --alle --top 5                 # Rollen-Score je Slot (--slot, --detail NAME)
uv run python scripts/benchmark.py --profil stuermer_torjaeger # absolute Maßstäbe (--detail NAME)
uv run python scripts/value.py --rolle gruppe_st --sort fv --nur-moneyball   # Fair Value
uv run python scripts/sellkeep.py                              # Sell/Keep eigener Kader
uv run python scripts/spiele.py [--zeige NAME]                 # Spiellisten erfassen / anzeigen
uv run python scripts/webapp.py                                # Kaderplaner, http://127.0.0.1:8700
```

`--save` fehlt → `$FM27_SAVE`, sonst „Aktiver Save“ aus CLAUDE.md. Weitere Optionen: `--help`.
Alle Skripte kennen `--db` und `--config-dir` (Tests nutzen `tests/fixtures/config/`).

## Wichtige Annahmen

- Stat-Namen in `spalten.yaml`: Zählwert `x` → `x_p90`; `x_pct`/`x_p90`/`x_avg`/`x_n` bleiben
  unverändert; Attribute tragen das Präfix `attr_`.
- Der Export mischt Dezimalzeichen (`"7,07"` vs. `2.01`): Default in `zahlenformat.dezimal`, Ausnahmen
  und Einheiten (`km`) pro Spalte (`{name, dezimal, einheit, typ}`). Nicht lesbare Werte → NULL + Warnung,
  nie stilles Falschparsen. Text-/Datumsfelder (`typ: text|date`) landen in `player_info`.
- Doppelte Header heißen wie bei pandas: `Endet` (Vertragsende), `Endet.1` (Leihende), `Freistöße`
  (Stat) / `Freistöße.1` (Attribut). Unlesbare Datumswerte brechen den Import ab (falsche Spaltenfolge).
- Leihe: Kader-Ansicht `Leihdauer` ("6.7.26 - 30.6.27") → `loan_start`/`loan_end`, `Ausgeliehen von` → Stammverein
  (`player_info`). Verliehene Eigengewächse haben als `club`/`league` den Leihverein und `ausgeliehen_von` =
  Werder Bremen; Leih-Zugänge haben `club` = Werder Bremen und den fremden Stammverein. Die Suche liefert
  das Leihende stattdessen als zweites `Endet` (`Endet.1`).
- Liga-Ranking: `config/ligen.yaml` (`ranking`, aus der FM-Ansicht abgetippt) → Tabelle `league_ranking`,
  Schlüssel Liga + Land (`Ansässig in`). `per90.load_wide` hängt `liga_rang` (1 = oben) und `liga_ansehen`
  an; der Import warnt bei Ligen ohne Eintrag. Perzentile laufen je Position + Liga + Land.
- Scouting-Spannen: Attribute `14-18` → `lo`/`hi` (`value` NULL, `masked=1`); Gehalt/Transferwert-Spannen →
  `wage_min`/`wage_max`, `value_min`/`value_max`.
- Transferwert-Spannen: `value_min`/`value_max`, `value` = Mittelwert; „Steht nicht zum Verkauf“ → NULL.
- Gehalt wird beim Import auf Jahreswerte umgerechnet (`gehalt.periode: jahr`; Import bricht ab, wenn
  der Export eine andere Periode zeigt).
- Perzentile nur innerhalb Position + Liga, Mindestgruppe und Mindestminuten aus `rollen.yaml`.
- Kosten/Saison = Jahresgehalt + Marktwert / Vertragsjahre (mind. 1 Jahr).
- Platzhalter-Schwellen (`min_gruppe`, `xg_delta_flag_p90`) in `rollen.yaml` nach dem ersten Export kalibrieren.
- Liga-Normalisierung (`value.py --liga-norm`) ist nur eine Hypothese und braucht `config/ligen.yaml`.
