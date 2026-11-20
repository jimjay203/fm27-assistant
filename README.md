# FM27-Assistent

Claude Code als Assistent für Football Manager 27: Subagents (`taktik`, `entwicklung`, `scouting`,
`analyst`), SQLite-Snapshots der Spieldaten und Python-Skripte für Moneyball-Auswertungen.
Regeln und aktiver Save stehen in [CLAUDE.md](CLAUDE.md).

**Stand:** Gerüst fertig und mit synthetischen Daten getestet. `config/spalten.yaml` ist bewusst leer –
es gibt noch keinen echten FM27-Export, also keine erfundenen Spaltennamen (`TODO(export)`).

## Setup (nur uv)

```
uv sync
uv run pytest
```

## Workflow

| Anlass | Export | Agent-Reihenfolge |
|---|---|---|
| Vor Transferfenster | Kader + Spielersuche (Zielpositionen) | analyst → taktik (Bedarf bestätigen) → scouting |
| Monatlich | Kader inkl. Stats + Attribute | analyst → entwicklung |
| Nach 3–5 Spielen / Taktikänderung | Team-/Spielstatistiken | analyst → taktik (Messkriterium aus log.md prüfen) |
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
```

`--save` fehlt → `$FM27_SAVE`, sonst „Aktiver Save“ aus CLAUDE.md. Weitere Optionen: `--help`.
Alle Skripte kennen `--db` und `--config-dir` (Tests nutzen `tests/fixtures/config/`).

## Wichtige Annahmen

- Stat-Namen in `spalten.yaml`: Zählwert `x` → `x_p90`; `x_pct`/`x_p90` bleiben unverändert;
  Attribute tragen das Präfix `attr_`.
- Gehalt wird beim Import auf Jahreswerte umgerechnet (`gehalt.periode` ist Pflicht, offener Punkt 6).
- Perzentile nur innerhalb Position + Liga, Mindestgruppe und Mindestminuten aus `rollen.yaml`.
- Kosten/Saison = Jahresgehalt + Marktwert / Vertragsjahre (mind. 1 Jahr).
- Platzhalter-Schwellen (`min_gruppe`, `xg_delta_flag_p90`) in `rollen.yaml` nach dem ersten Export kalibrieren.
- Liga-Normalisierung (`value.py --liga-norm`) ist nur eine Hypothese und braucht `config/ligen.yaml`.
