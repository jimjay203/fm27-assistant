# Torwart-Attribute in FM27: was die Match-Engine belohnt (FM-Arena-Test)

Quelle: FM-Arena, „Attribute importance by position in FM27 – a test on my own tactic“ (Autor Purity),
TW-Abschnitt vom 14.11.2026, https://fm-arena.com/threads/attribute-importance-by-position-in-fm27-a-test-on-my-own-tactic.125/
**FM27** (Build vom 12.11.2026). Gelesen am 25.11.2026 (real). Nicht selbst nachgeprüft.

## Methode (laut Autor)
- Match-Engine von FM27 außerhalb des Spiels nachgespielt: Brentford, 3-4-2-1, die 38 echten Premier-League-Spiele.
- Nur der Torwart wird verändert: Jedes der 48 sichtbaren Attribute bekommt seinen echten Wert ± zufällig bis 5.
  Die 10 Feldspieler bleiben gleich.
- 50.000 Konfigurationen × 4 Seeds = 200.000 Spiele; taktische Wirksamkeit fest auf 100.
- Regression auf Tordifferenz (Spielpaarung als fester Effekt). Einheit: +1 Stufe eines TW-Attributs über 38 Spiele.
- „Bestätigt“ = |z| > 2 mit gleichem Vorzeichen in beiden zufälligen Datenhälften.
- **Lücke:** Die TW-Rolle ist nicht angegeben. Speziell für den Libero-Torhüter gibt es keinen Test.

## Ergebnis (+1 Stufe, pro 38-Spiele-Saison)
| Attribut (DE) | EN | Tordifferenz | Punkte (±95 %) | Bestätigt |
|---|---|---|---|---|
| Beweglichkeit | Agility | +0,66 | +0,50 (0,05) | ja |
| Reflexe | Reflexes | +0,60 | +0,45 (0,06) | ja |
| Hohe Bälle | Aerial Reach | +0,24 | +0,19 (0,05) | ja |
| Konzentration | Concentration | +0,18 | +0,13 (0,05) | ja |
| Wichtige Spiele (versteckt) | Important Matches | +0,11 | +0,09 (0,05) | ja |
| Halten | Handling | +0,06 | +0,07 (0,05) | nein |
| Antritt | Acceleration | +0,10 | +0,07 (0,05) | nein (z 3,1, eine Hälfte < 2) |
| Strafraumkontrolle | Command of Area | +0,09 | +0,07 (0,05) | nein |
| Antizipation | Anticipation | +0,10 | +0,06 (0,05) | nein |
| Herauslaufen (Tendenz) | Rushing Out | −0,06 | −0,04 (0,05) | nein |

Laut Autor sind Stellungsspiel, Eins gegen Eins, Herauslaufen und Strafraumkontrolle bei dieser Stichprobe
„nicht von null unterscheidbar“. Für Schnelligkeit (Pace) wird kein TW-Wert genannt.
Zum Vergleich bei Feldspielern (teamweit): Antritt und Schnelligkeit je +0,34 Tordifferenz pro Stufe.

Der Wert einer Stufe hängt vom Niveau ab, angegeben in Punkten je Stufe:
- Beweglichkeit 12–16: +0,63; 16–20: +0,36
- Reflexe 12–16: +0,34; 16–20: +0,49

## Folgerungen
- Beim Torwart zählen fast nur Beweglichkeit und Reflexe, etwa 0,5 Punkte pro Stufe und Saison.
  Antritt bringt rund ein Siebtel davon und ist nicht gesichert.
- Libero-Torhüter: Die Key-Attribute nach sortitoutsi/FM26 ([rollen-attribute.md](rollen-attribute.md)) sind
  Herauslaufen, Antizipation und Entscheidungen. Für keines davon zeigt der FM27-Test einen gesicherten Effekt.
  Die Rolle wählt man deshalb nach dem taktischen Zweck (hohe Linie absichern), nicht nach dem Attributprofil.
- Trainingsfokus Torwart: Beweglichkeit und Reflexe vor allem anderen.

## Prüfung GK-Gewichte (fm-scoring, [attribut-gewichte.md](attribut-gewichte.md)), 25.11.2026 real
Wirksam ist nur `ability.archetypen.GK` in `config/rollen.yaml`. sellkeep.py nutzt es für Ability-vs-Alter bei
Torhütern ≤ 23 Jahre mit < 900 Minuten. `gruppe_gk.attribute_prior` ist aus (`attribut_gewicht` 0.0).

| | Alt (fm-scoring) | Testbasiert (Punkte-Effekt, Beweglichkeit = 5) |
|---|---|---|
| Gewichte | Beweglichkeit 5, Reflexe 5, Antritt 3, Hohe Bälle 3, Stellungsspiel 2, Strafraumkontrolle 2, Antizipation/Kommunikation/Nervenstärke/Konzentration/Entscheidungen/Eins gegen Eins je 1, Halten/Abschlag/Abwurf je 0,5 | Beweglichkeit 5, Reflexe 4,5, Hohe Bälle 2, Konzentration 1,5, Halten/Antritt/Strafraumkontrolle/Antizipation je 0,5 |
| Anteil Beweglichkeit + Reflexe | 36 % | 63 % |
| Anteil Antritt | 11 % | 3,3 % |

Vergleich auf dem Such-Snapshot vom 14.07.2027 (457 TW; fremde Attribute als Mitte der Scouting-Spanne):
- Rangkorrelation alt/neu 0,92. Die Spitze der Bundesliga ändert sich kaum: Nicolas und Rønnow bleiben 1 und 2.
- Ausreißer verschieben sich um mehr als 100 Ränge. Nach oben gehen TW mit Beweglichkeit/Reflexe, aber wenig
  Antritt, z. B. Mitov 249 → 108. Nach unten gehen TW mit viel Antritt, z. B. Delfim 63 → 186.
- Werder (Kader-Snapshot 04.09.2027): Hein 13,71 → 14,47, Schlager 13,16 → 13,97. Die Reihenfolge bleibt gleich.

**Umgestellt am 25.11.2026 (real), Entscheidung Jimmy:** Beide Stellen in `config/rollen.yaml` nutzen jetzt die
testbasierten Gewichte.
