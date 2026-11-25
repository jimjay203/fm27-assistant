# Attribut-Gewichte und Altersbenchmark (extern, für FM27 ungeprüft)

**Status:** Fremdwerte, nicht selbst validiert. Sie stehen hier, damit `attribute_prior` in
`config/rollen.yaml` eine dokumentierte Herkunft hat. Entscheidungen nicht allein darauf stützen.
`attribut_gewicht` bleibt deshalb bei 0.0 (aus), bis Jimmy es bewusst einschaltet.

## Herkunft
- Tabellen aus FMMT-27 (`FMMT 27.html`, Konstanten `AW`, `AGEB`; Stand 1.0.5, 2026-11-18). Dort
  übernommen aus Jamie Boldens **fm-scoring** (`weights/fm27.toml`, laut Kommentar "tuned toward
  harvestgreen22's FM27 attribute testing"). Quelle der Tabellen hier: Lesung der FMMT-Datei, nicht
  gegen das fm-scoring-Original abgeglichen.
- Lizenz dieser Tabellen: MIT, Copyright (c) 2026 Jamie Bolden. Der Rest von FMMT-27 ist GPL-3.0
  und wird nicht übernommen.
- Gewichte sind kleine ganze Zahlen (Antritt und Schnelligkeit überall 5): Setzungen, keine
  hergeleiteten Koeffizienten.

## Gewichte je Archetyp (Attribut → Gewicht; Skala 1–20, Score = Σ(Attribut·Gewicht) / Σ Gewicht)
| Archetyp | Gewichte |
|---|---|
| CB | Antritt 5, Sprunghöhe 5, Schnelligkeit 5, Antizipation 3, Kopfballtechnik 3, Kraft 3, Nervenstärke 2, Passen 2, Stellungsspiel 2, Entscheidungen 1, Ballannahme 1, Ausdauer 1, Tackling 1, Einsatzfreude 1 |
| WB/6 | Antritt 5, Schnelligkeit 5, Ausdauer 4, Antizipation 3, Dribbling 3, Einsatzfreude 3, Passen 2, Stellungsspiel 2, Teamwork 2, Nervenstärke 1, Entscheidungen 1, Ballannahme 1, Kraft 1, Tackling 1 |
| 10 | Antritt 5, Dribbling 5, Schnelligkeit 5, Antizipation 3, Nervenstärke 2, Ohne Ball 2, Passen 2, Ausdauer 2, Einsatzfreude 2, Entscheidungen 1, Abschluss 1, Ballannahme 1, Kraft 1, Teamwork 1 |
| 9 | Antritt 5, Sprunghöhe 5, Schnelligkeit 5, Antizipation 3, Dribbling 3, Abschluss 3, Nervenstärke 2, Ohne Ball 2, Ausdauer 2, Einsatzfreude 2, Entscheidungen 1, Ballannahme 1, Kopfballtechnik 1, Kraft 1, Teamwork 1 |
| GK | Beweglichkeit 5, Reflexe 5, Antritt 3, Hohe Bälle 3, Stellungsspiel 2, Strafraumkontrolle 2, Antizipation 1, Kommunikation 1, Nervenstärke 1, Konzentration 1, Entscheidungen 1, Eins gegen Eins 1, Halten 0,5, Abschlag 0,5, Abwurf 0,5 |

**Abweichung GK (25.11.2026 real, Entscheidung Jimmy):** In `config/rollen.yaml` (`ability.archetypen.GK`,
`gruppe_gk.attribute_prior`) stehen nicht die fm-scoring-Werte oben. Dort stehen Gewichte nach dem FM27-Test von
FM-Arena: Beweglichkeit 5, Reflexe 4,5, Hohe Bälle 2, Konzentration 1,5, Halten/Antritt/Strafraumkontrolle/
Antizipation je 0,5. Herleitung und Vergleich: [tw-attribute-fm27.md](tw-attribute-fm27.md).

Übersetzung EN → DE wie in `config/live_spalten.yaml`. Unsicher: *Aerial Reach → Hohe Bälle*.

## Positions-Zuordnung (FMMT-eigene Setzung, kein FM-Wissen)
GK→GK · IV→CB · AV/WB/DM→WB/6 · ZM→besserer Wert aus WB/6 und 10 · Flügel/AM→10 · ST→9.

## Altersbenchmark (Ability-Score auf 1–20 je Alter)
| Alter | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|
| Benchmark | 10,3 | 10,9 | 11,5 | 12,2 | 12,6 | 12,9 | 13,2 | 13,4 | 13,7 | 13,8 |

"vs Alter" = bester Archetyp-Score / Benchmark · 100. 100 % bedeutet laut Quelle "auf Kurs für einen
oberen Championship- bis unteren Premier-League-Spieler". Älter als 24: kein Benchmark vorhanden.

## Grenzen
- Gilt nur mit **exakten** Attributen, also nur für eigene Spieler (siehe `config/live_spalten.yaml`).
- Hidden Attributes/CA/PA fließen nicht ein, Persönlichkeit und Taktik-Rollen ebenso wenig.
