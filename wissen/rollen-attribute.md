# Schlüsselattribute je Rolle

Quelle: sortitoutsi.net, „FM26: Important Attributes for Every Role“ (Autor edgardavids8, Staff, 08.11.2025),
https://sortitoutsi.net/content/75078/fm26-important-attributes-for-every-role. **Aus FM26; laut Jimmy 1:1 auf
FM27 übertragbar** (Rollensystem mit/ohne Ball identisch). Maschinenlesbar: `config/rollen_attribute.yaml`.

- **Key** = wichtigste Attribute (laut Autor wichtiger als Preferred), **Preferred** = nützlich,
  **Unnecessary** = irrelevant.
- Rollen ohne Ball: nur je 3 Key-Attribute veröffentlicht, kein Preferred (Nachfrage in den Kommentaren unbeantwortet).
- Nicht enthalten: Standard-Rollen ohne Ball (Mittelstürmer, Innenverteidiger, Außenverteidiger, DM, Flügelspieler,
  Offensiver Mittelfeldspieler, Torwart ohne Ball).
- Deutsche Rollennamen nach [rollen.md](rollen.md). Unsicher: Half-Back = Abkippender Sechser,
  Dropping Defensive Midfielder = Halbverteidiger.
- Verwendung: Rollenabhängiger Mindestfilter im Scouting ersetzt den positionsneutralen Kernfilter aus
  [rollen-meta.md](rollen-meta.md) (Liga-Schwelle von dort, Bundesliga 12). Umsetzung: `scripts/rollen_attr.py`,
  Spalten key_mit/key_ohne/key_fehlt/key_unsicher in `rollen.py` (weist aus, verwirft nicht).


## TW

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Torwart (Goalkeeper) | mit Ball | Hohe Bälle, Strafraumkontrolle, Kommunikation, Halten, Reflexe, Beweglichkeit, Konzentration, Stellungsspiel | Abschlag, Eins gegen Eins, Abwurf, Antizipation, Entscheidungen | Exzentrizität |
| Ballspielender Torhüter (Ball-Playing Goalkeeper) | mit Ball | Hohe Bälle, Strafraumkontrolle, Kommunikation, Halten, Abschlag, Reflexe, Beweglichkeit, Konzentration, Stellungsspiel | Exzentrizität, Eins gegen Eins, Abwurf, Antizipation, Nervenstärke, Entscheidungen, Passen | – |
| Kompromissloser Torhüter (No-Nonsense Goalkeeper) | mit Ball | Hohe Bälle, Strafraumkontrolle, Kommunikation, Halten, Reflexe, Beweglichkeit, Konzentration, Stellungsspiel | Eins gegen Eins, Antizipation, Entscheidungen | Exzentrizität, Passen |
| Linientorhüter (Line-Holding Keeper) | ohne Ball | Stellungsspiel, Konzentration | – | – |
| Libero-Torhüter (Sweeper Keeper) | ohne Ball | Herauslaufen (Tendenz), Antizipation, Entscheidungen | – | – |

## IV

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Innenverteidiger (Centre-Back) | mit Ball | Kopfballtechnik, Deckung, Tackling, Antizipation, Stellungsspiel, Sprunghöhe, Kraft | Aggressivität, Mut, Nervenstärke, Konzentration, Entscheidungen, Schnelligkeit | Passen |
| Spielaufbauender Innenverteidiger (Ball-Playing Centre-Back) | mit Ball | Kopfballtechnik, Deckung, Passen, Tackling, Antizipation, Nervenstärke, Stellungsspiel, Sprunghöhe, Kraft | Ballannahme, Technik, Aggressivität, Mut, Konzentration, Entscheidungen, Übersicht, Schnelligkeit | – |
| Kompromissloser Innenverteidiger (No-Nonsense Centre-Back) | mit Ball | Kopfballtechnik, Deckung, Tackling, Antizipation, Stellungsspiel, Sprunghöhe, Kraft | Aggressivität, Mut, Konzentration, Schnelligkeit | Passen, Nervenstärke |
| Halbraumverteidiger (Wide Centre-Back) | mit Ball | Kopfballtechnik, Deckung, Tackling, Antizipation, Stellungsspiel, Sprunghöhe, Kraft | Dribbling, Aggressivität, Mut, Nervenstärke, Konzentration, Entscheidungen, Einsatzfreude, Antritt, Beweglichkeit, Schnelligkeit, Ausdauer | Passen |
| Aufrückender Innenverteidiger (Advanced Centre-Back) | mit Ball | Kopfballtechnik, Deckung, Passen, Tackling, Technik, Antizipation, Nervenstärke, Entscheidungen, Stellungsspiel, Teamwork, Sprunghöhe, Kraft | Dribbling, Ballannahme, Aggressivität, Mut, Konzentration, Übersicht, Schnelligkeit, Ausdauer | – |
| Hinterlaufender Halbraumverteidiger (Overlapping Centre-Back) | mit Ball | Flanken, Kopfballtechnik, Deckung, Tackling, Antizipation, Einsatzfreude, Sprunghöhe, Schnelligkeit, Ausdauer, Kraft | Dribbling, Technik, Aggressivität, Mut, Nervenstärke, Konzentration, Entscheidungen, Ohne Ball, Stellungsspiel, Antritt, Beweglichkeit | – |
| Absichernder Innenverteidiger (Covering Centre-Back) | ohne Ball | Antizipation, Schnelligkeit, Deckung | – | – |
| Stoppender Innenverteidiger (Stopping Centre-Back) | ohne Ball | Aggressivität, Tackling, Kraft | – | – |
| Absichernder Halbraumverteidiger (Covering Wide Centre-Back) | ohne Ball | Antizipation, Schnelligkeit, Deckung | – | – |
| Stoppender Halbraumverteidiger (Stopping Wide Centre-Back) | ohne Ball | Aggressivität, Tackling, Kraft | – | – |

## AV

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Außenverteidiger (Full-Back) | mit Ball | Deckung, Tackling, Antizipation, Konzentration, Stellungsspiel, Teamwork, Antritt | Flanken, Dribbling, Passen, Technik, Entscheidungen, Einsatzfreude, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Inverser Außenverteidiger (Inside Full-Back) | mit Ball | Kopfballtechnik, Deckung, Tackling, Antizipation, Stellungsspiel, Kraft | Dribbling, Aggressivität, Mut, Nervenstärke, Konzentration, Entscheidungen, Einsatzfreude, Antritt, Beweglichkeit, Sprunghöhe, Schnelligkeit, Ausdauer | – |
| Abwartender Außenverteidiger (Holding Full-Back) | ohne Ball | Stellungsspiel, Konzentration, Deckung | – | – |
| Pressender Außenverteidiger (Pressing Full-Back) | ohne Ball | Aggressivität, Einsatzfreude, Antizipation | – | – |

## AV/FV

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Inverser Flügelverteidiger (Inside Wing-Back) | mit Ball | Passen, Tackling, Antizipation, Nervenstärke, Entscheidungen, Stellungsspiel, Teamwork, Antritt | Ballannahme, Deckung, Technik, Konzentration, Einsatzfreude, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Spielmachender Flügelverteidiger (Playmaking Wing-Back) | mit Ball | Ballannahme, Passen, Tackling, Technik, Nervenstärke, Entscheidungen, Stellungsspiel, Teamwork, Übersicht, Antritt | Flanken, Dribbling, Deckung, Antizipation, Konzentration, Ohne Ball, Einsatzfreude, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Flügelverteidiger (Wing-Back) | mit Ball | Flanken, Deckung, Tackling, Teamwork, Einsatzfreude, Antritt, Schnelligkeit, Ausdauer | Dribbling, Ballannahme, Passen, Technik, Antizipation, Konzentration, Entscheidungen, Ohne Ball, Stellungsspiel, Beweglichkeit, Balance | – |

## FV

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Vorgeschobener Flügelverteidiger (Advanced Wing-Back) | mit Ball | Flanken, Dribbling, Technik, Ohne Ball, Teamwork, Einsatzfreude, Antritt, Beweglichkeit, Schnelligkeit, Ausdauer | Ballannahme, Deckung, Passen, Tackling, Antizipation, Entscheidungen, Kreativität, Stellungsspiel, Balance | – |
| Abwartender Flügelverteidiger (Holding Wing-Back) | ohne Ball | Stellungsspiel, Konzentration, Deckung | – | – |
| Pressender Flügelverteidiger (Pressing Wing-Back) | ohne Ball | Aggressivität, Einsatzfreude, Antizipation | – | – |

## DM

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Defensiver Mittelfeldspieler (Defensive Midfielder) | mit Ball | Tackling, Antizipation, Konzentration, Stellungsspiel, Teamwork | Ballannahme, Deckung, Passen, Aggressivität, Nervenstärke, Entscheidungen, Einsatzfreude, Ausdauer, Kraft | – |
| Box-to-Box-Spieler (Box-to-Box Midfielder) | mit Ball | Passen, Tackling, Ohne Ball, Teamwork, Einsatzfreude, Ausdauer | Dribbling, Abschluss, Ballannahme, Weitschüsse, Technik, Aggressivität, Antizipation, Nervenstärke, Entscheidungen, Stellungsspiel, Antritt, Balance, Schnelligkeit, Kraft | – |
| Box-to-Box-Spielmacher (Box-to-Box Playmaker) | mit Ball | Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht, Einsatzfreude, Ausdauer | Dribbling, Deckung, Tackling, Antizipation, Stellungsspiel, Antritt, Beweglichkeit, Balance, Schnelligkeit | – |
| Tiefer Spielmacher (Deep-Lying Playmaker) | mit Ball | Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht | Deckung, Tackling, Antizipation, Konzentration, Stellungsspiel, Einsatzfreude, Balance, Ausdauer | – |
| Abkippender Sechser (Half-Back) | mit Ball | Kopfballtechnik, Deckung, Tackling, Antizipation, Konzentration, Stellungsspiel, Teamwork, Sprunghöhe, Kraft | Ballannahme, Passen, Aggressivität, Mut, Nervenstärke, Entscheidungen, Einsatzfreude, Ausdauer | – |
| Halbverteidiger (Dropping Defensive Midfielder) | ohne Ball | Stellungsspiel, Entscheidungen, Antizipation | – | – |
| Pressender Sechser (Pressing Defensive Midfielder) | ohne Ball | Aggressivität, Einsatzfreude, Antizipation | – | – |
| Abschirmender Sechser (Screening Defensive Midfielder) | ohne Ball | Stellungsspiel, Konzentration, Deckung | – | – |
| Flügelsichernder Sechser (Wide Covering Defensive Midfielder) | ohne Ball | Antizipation, Schnelligkeit, Einsatzfreude | – | – |

## ZM

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Zentraler Mittelfeldspieler (Central Midfielder) | mit Ball | Ballannahme, Passen, Tackling, Entscheidungen, Teamwork | Technik, Antizipation, Nervenstärke, Konzentration, Ohne Ball, Stellungsspiel, Übersicht, Einsatzfreude, Ausdauer | – |
| Vorgeschobener Spielmacher (Advanced Playmaker) | mit Ball | Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht | Flanken, Dribbling, Antizipation, Kreativität, Antritt, Beweglichkeit | – |
| Spielmacher (Midfield Playmaker) | mit Ball | Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht | Dribbling, Tackling, Antizipation, Kreativität, Stellungsspiel, Einsatzfreude, Beweglichkeit, Ausdauer | – |
| Weiter Achter (Wide Central Midfielder) | mit Ball | Ballannahme, Passen, Tackling, Entscheidungen, Teamwork | Flanken, Dribbling, Technik, Antizipation, Nervenstärke, Konzentration, Ohne Ball, Stellungsspiel, Übersicht, Einsatzfreude, Beweglichkeit, Ausdauer | – |
| Pressender Achter (Pressing Central Midfielder) | ohne Ball | Aggressivität, Einsatzfreude, Antizipation | – | – |
| Abschirmender Achter (Screening Central Midfielder) | ohne Ball | Stellungsspiel, Konzentration, Deckung | – | – |
| Flügelsichernder Achter (Wide Covering Central Midfielder) | ohne Ball | Antizipation, Schnelligkeit, Einsatzfreude | – | – |

## M außen

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Äußerer Mittelfeldspieler (Wide Midfielder) | mit Ball | Flanken, Passen, Technik, Teamwork, Einsatzfreude, Schnelligkeit, Ausdauer | Dribbling, Ballannahme, Antizipation, Nervenstärke, Ohne Ball, Übersicht, Antritt, Beweglichkeit | – |
| Mitarbeitender Außenspieler (Tracking Wide Midfielder) | ohne Ball | Deckung, Einsatzfreude, Ausdauer | – | – |
| Äußerer Umschaltspieler (Wide Outlet Wide Midfielder) | ohne Ball | Ohne Ball, Schnelligkeit, Antizipation | – | – |

## Flügel (M/OM R/L)

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Halbraumflügel (Inside Winger) | mit Ball | Dribbling, Ballannahme, Technik, Nervenstärke, Teamwork, Antritt, Beweglichkeit | Flanken, Weitschüsse, Passen, Antizipation, Kreativität, Ohne Ball, Übersicht, Einsatzfreude, Balance, Schnelligkeit, Ausdauer | – |
| Äußerer Spielmacher (Playmaking Winger) | mit Ball | Flanken, Dribbling, Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht, Antritt | Antizipation, Kreativität, Einsatzfreude, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Flügelspieler (Winger) | mit Ball | Flanken, Dribbling, Technik, Teamwork, Antritt, Beweglichkeit, Schnelligkeit | Ballannahme, Passen, Antizipation, Kreativität, Ohne Ball, Einsatzfreude, Balance, Ausdauer | – |
| Außenstürmer (Wide Forward) | mit Ball | Dribbling, Ballannahme, Technik, Antizipation, Ohne Ball, Antritt, Beweglichkeit, Schnelligkeit | Flanken, Abschluss, Passen, Nervenstärke, Kreativität, Einsatzfreude, Balance, Ausdauer | – |
| Inverser Außenstürmer (Inside Forward) | mit Ball | Dribbling, Ballannahme, Technik, Antizipation, Nervenstärke, Ohne Ball, Antritt, Beweglichkeit | Flanken, Abschluss, Weitschüsse, Passen, Kreativität, Übersicht, Einsatzfreude, Balance, Schnelligkeit, Ausdauer | – |
| Inverser Umschaltflügelspieler (Inside Outlet Winger) | ohne Ball | Ohne Ball, Entscheidungen, Antizipation | – | – |
| Mitarbeitender Flügelspieler (Tracking Winger) | ohne Ball | Deckung, Einsatzfreude, Ausdauer | – | – |
| Umschaltflügelspieler (Wide Outlet Winger) | ohne Ball | Ohne Ball, Schnelligkeit, Antizipation | – | – |

## OM zentral

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Offensiver Mittelfeldspieler (Attacking Midfielder) | mit Ball | Ballannahme, Weitschüsse, Passen, Technik, Nervenstärke, Kreativität, Ohne Ball | Flanken, Dribbling, Abschluss, Antizipation, Entscheidungen, Übersicht, Antritt, Beweglichkeit | – |
| Halbraumspieler (Channel Midfielder) | mit Ball | Flanken, Ballannahme, Passen, Technik, Nervenstärke, Ohne Ball, Einsatzfreude, Antritt | Dribbling, Weitschüsse, Antizipation, Entscheidungen, Kreativität, Übersicht, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Freigeist (Free Role) | mit Ball | Dribbling, Ballannahme, Weitschüsse, Passen, Technik, Nervenstärke, Kreativität, Ohne Ball, Übersicht | Flanken, Abschluss, Antizipation, Entscheidungen, Antritt, Beweglichkeit | – |
| Zweiter Stürmer (Second Striker) | mit Ball | Abschluss, Ballannahme, Antizipation, Nervenstärke, Ohne Ball, Antritt | Dribbling, Weitschüsse, Passen, Technik, Konzentration, Entscheidungen, Einsatzfreude, Beweglichkeit, Schnelligkeit, Ausdauer | – |
| Zentraler Umschaltzehner (Central Outlet Attacking Midfielder) | ohne Ball | Ohne Ball, Entscheidungen, Antizipation | – | – |
| Ausweichender Umschaltzehner (Splitting Outlet Attacking Midfielder) | ohne Ball | Ohne Ball, Schnelligkeit, Antizipation | – | – |
| Mitarbeitender Zehner (Tracking Attacking Midfielder) | ohne Ball | Deckung, Einsatzfreude, Ausdauer | – | – |

## ST

| Rolle | Phase | Key | Preferred | Unnecessary |
|---|---|---|---|---|
| Mittelstürmer (Centre Forward) | mit Ball | Abschluss, Ballannahme, Kopfballtechnik, Technik, Nervenstärke, Ohne Ball, Antritt, Kraft | Dribbling, Passen, Antizipation, Entscheidungen, Beweglichkeit, Balance, Sprunghöhe, Schnelligkeit | – |
| Halbraumstürmer (Channel Forward) | mit Ball | Dribbling, Abschluss, Ballannahme, Technik, Nervenstärke, Ohne Ball, Einsatzfreude, Antritt | Flanken, Kopfballtechnik, Passen, Antizipation, Entscheidungen, Beweglichkeit, Balance, Schnelligkeit, Ausdauer | – |
| Hängende Spitze (Deep-Lying Forward) | mit Ball | Abschluss, Ballannahme, Technik, Nervenstärke, Ohne Ball, Kraft | Dribbling, Passen, Antizipation, Entscheidungen, Teamwork, Übersicht, Balance | – |
| Falsche Neun (False Nine) | mit Ball | Dribbling, Ballannahme, Passen, Technik, Nervenstärke, Entscheidungen, Ohne Ball, Teamwork, Übersicht, Antritt | Abschluss, Antizipation, Kreativität, Beweglichkeit, Balance | – |
| Knipser (Poacher) | mit Ball | Abschluss, Kopfballtechnik, Antizipation, Nervenstärke, Konzentration, Ohne Ball, Antritt | Ballannahme, Technik, Entscheidungen, Balance | – |
| Zielspieler (Target Forward) | mit Ball | Abschluss, Kopfballtechnik, Aggressivität, Mut, Nervenstärke, Ohne Ball, Balance, Sprunghöhe, Kraft | Ballannahme, Antizipation, Entscheidungen, Teamwork | – |
| Zentraler Umschaltstürmer (Central Outlet Centre Forward) | ohne Ball | Ohne Ball, Entscheidungen, Antizipation | – | – |
| Ausweichender Umschaltstürmer (Splitting Outlet Centre Forward) | ohne Ball | Ohne Ball, Schnelligkeit, Antizipation | – | – |
| Mitarbeitender Mittelstürmer (Tracking Centre Forward) | ohne Ball | Deckung, Einsatzfreude, Ausdauer | – | – |
