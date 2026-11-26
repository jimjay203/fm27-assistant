# Wissen (FM27)

Regel: **FM27 > Vorwissen.** Nur FM27-bezogene Inhalte übernehmen; ältere Versionen kennzeichnen.

## Quellen
- Offizielles FM27-Handbuch und Release-Notes von Sports Interactive
- SI-Forum (Tactics & Training)
- FM-Arena (Match-Engine-Tests: welche Attribute wirken)
- FM Scout / sortitoutsi (eigene Ansichten, Tools, Exporte)

- FMMT-27 (github.com/fmoreoo/FMMT-27, GPL-3.0): lokaler Reader als Datenquelle, siehe `scripts/live.py`
- fm-scoring (Jamie Bolden, MIT): Attribut-Gewichte, siehe [attribut-gewichte.md](attribut-gewichte.md)
- Zweierkette: Rollenkatalog (aus FM26, für FM27 ungeprüft), siehe [rollen.md](rollen.md)
- fm-tactics-lab (github.com/lqf0624/fm-tactics-lab, MIT), `native/fm27_tactic_bindings.h` (v1126, Build 27.1.1):
  Slot-Tabelle mit den wählbaren Rollen je Position/Phase inkl. Kontextregeln, aufgelöst mit FM.UI.dll-Enums
  (26.11.2026 real) -> [rollen.md](rollen.md) Abschnitt "Rollenauswahl je Position", `config/rollen_positionen.yaml`.
  Beschriftungen der Team-/Spieleranweisungen liegen nur im nicht öffentlichen `catalog.json` der EXE (nicht genutzt).
  Das Tool selbst (Batch-Simulation mit der Original-Engine) ist nicht im Einsatz (Entscheidung Jimmy, 26.11.2026 real).
- Erfolgsmessung je Rolle (Vorschlag von Claude, ungeprüft): [rollen-kpis.md](rollen-kpis.md), maschinenlesbar `config/rollen_kpis.yaml`
- FM Stag "What does Good look like in FM24?": Benchmarks, siehe [benchmarks-fm24.md](benchmarks-fm24.md) (Anker für FM27 neu berechnet: `config/anker_fm27.yaml`)
- Teamanweisungen mit Ball, alle Stufen und UI-Texte (FM27-Screenshots 03.07.2027): [teamanweisungen.md](teamanweisungen.md)
- Rollen-Verhalten ohne Ball (Farblogik) und Meta-Attribute je Liga (Tabelle eines erfahrenen Spielers, Version unbekannt): [rollen-meta.md](rollen-meta.md)
- FM-Arena-Test Torwart-Attribute (FM27, Wirkung je Stufe) und Prüfung der GK-Gewichte: [tw-attribute-fm27.md](tw-attribute-fm27.md)
- FM26 Moneyball Stat Benchmarks (Urheber unbekannt): [benchmarks-fm26.md](benchmarks-fm26.md), Schwellen nicht übernommen, Abgleich mit FM27 dort

https://fm.zweierkette.de/handbuch/fm-spielerrollen-liste/
https://fm.zweierkette.de/handbuch/spielerattribute-football-manager/
https://fm.zweierkette.de/taktik/so-funktionieren-spielerrollen/
https://fm.zweierkette.de/taktik/alle-spielerrollen-fm/
https://fm.zweierkette.de/taktik/fm-passspiel-kurz-vertikal/
https://fm-arena.com/threads/inside-the-fm27-match-engine-how-it-actually-works.140/
https://fm-arena.com/threads/player-attributes.59/
https://fm-arena.com/threads/fm27-playbook-27-1-0-what-the-tests-say-wins-matches-ai-analysis.221/
https://fm-arena.com/threads/attribute-importance-by-position-in-fm27-a-test-on-my-own-tactic.125/