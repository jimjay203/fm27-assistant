# Rollen-Verhalten ohne Ball und Meta-Attribute (Tabelle eines erfahrenen Spielers)

Quelle: Tabelle von einem erfahrenen FM-Spieler, an Jimmy weitergegeben (03.07.2027 in-game). FM-Version und
Herleitung unbekannt, **für FM27 ungeprüft**. Englische Rollennamen; Zuordnung zu den deutschen Namen aus
[rollen.md](rollen.md) ist eine Annahme, wo nicht anders vermerkt.

## Farblogik der Rollen ohne Ball (OOP)
| Farbe | Bedeutung laut Tabelle |
|---|---|
| Gelb | unterstützt Angriffs- und Defensivumschalten (Grundrolle) |
| Orange | Fokus Defensive: verteidigt etwas höher, verlässt die Linie früher, fällt bei längerem gegnerischem Ballbesitz aber tiefer als andere Rollen |
| Blau | Fokus Angriff: braucht länger zurück in die Defensivform, steht höher für das Umschalten nach vorn ("Outlet") |

| Bereich | Gelb | Orange | Blau | ohne Farbe |
|---|---|---|---|---|
| AV | Fullback | – | – | Pressing Fullback, Holding Fullback |
| FV | – | Holding Wingback | – | Wingback, Pressing Wingback |
| IV | – | – | – | Centreback, Stopping, Covering |
| DM | Defensive Midfielder | Dropping DM, Pressing DM, Screening DM (Abschirmender Sechser), Wide Covering DM (Flügelsichernder Sechser) | – | – |
| M außen | Wide Midfielder | Tracking Wide Midfielder | Wide Outlet Midfielder | – |
| ZM | Central Midfielder | Screening CM, Wide Covering CM | – | Pressing CM |
| Flügel (OM) | Winger | Tracking Winger (Mitarbeitender Flügelspieler) | Inside Outlet Winger (Inverser Umschaltflügelspieler), Wide Outlet Winger (Umschaltflügelspieler) | – |
| OM z | Attacking Midfielder | Tracking AM (Mitarbeitender Zehner) | Central Outlet AM (Zentraler Umschaltzehner), Splitting Outlet AM (Ausweichender Umschaltzehner) | – |
| ST | – | Tracking Centreforward (Mitarbeitender Mittelstürmer) | Central Outlet CF (Zentraler Umschaltstürmer), Splitting Outlet CF (Ausweichender Umschaltstürmer) | Centreforward |

Abweichung zu rollen.md: Die Tabelle nennt "Dropping Defensive Midfielder" als Rolle ohne Ball; rollen.md führt
dort "Halbverteidiger". UI-Name in FM27 nicht geprüft.

Folge für Werder (Standard 2027/28): 5 Rollen ohne Ball orange (Lynen, Stage, beide Flügel, Chuki), keine blaue,
ST neutral. Gut für Ballbesitz/Pressing, schwach für Konter: Für Konter-Szenarien einen Flügel ohne Ball auf
Umschaltflügelspieler (blau) stellen.

## Rollenzuordnung mit Ball (Auszug, Annahmen)
Inside Fullback = Inverser Außenverteidiger (schiebt neben den IV, laut Jimmy) · Inside Wingback = Inverser
Flügelverteidiger (neben den DM) · Channel Forward = Halbraumstürmer · Deep Lying Forward = vermutlich Hängende
Spitze · Channel Midfielder = vermutlich Halbraumspieler.

## Meta-Attribute und Schwellen
| Profil | Attribute (Mindestwert in der obersten Liga) |
|---|---|
| Baseline (alle Feldrollen) | Antritt, Aggressivität, Konzentration, Ausdauer, Einsatzfreude, Sprunghöhe; beim AV zusätzlich Mut (Zuordnung der Spalte unsicher) |
| Destroyer (zusätzlich) | Antizipation, Entscheidungen, Teamwork, Tackling, Mut, Stellungsspiel, Kopfballtechnik |
| Creator (zusätzlich) | Dribbling, Flanken, Ohne Ball, Übersicht, Ballannahme, Technik |

Schwelle je Liga-Stufe: Elite 12 · L1 11 · L2 10 · L3 9 · L4 8. Welche Ligen "Elite" sind, sagt die Tabelle
nicht (Annahme: Bundesliga, Liga-Rang 4, Ansehen "Exzellent").

Hybridrollen: Spieler, der zerstören und danach gestalten soll, braucht Destroyer- und Creator-Attribute.

Abgleich mit [attribut-gewichte.md](attribut-gewichte.md): Dort (FM-Arena) sind Antritt und Schnelligkeit die
stärksten Hebel; hier zählen zusätzlich Aggressivität, Konzentration, Einsatzfreude als "Meta". Widerspruch
nicht aufgelöst; Schnelligkeit fehlt hier. Verwendung: als Mindestfilter (Gegenprobe), nicht als Gewichtung.
