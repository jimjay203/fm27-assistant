# FM26 Moneyball Stat Benchmarks (aus FM26, für FM27 ungeprüft)

**Quelle:** Tabelle „⚽ FM26 Moneyball Stat Benchmarks“ (CSV), von Jimmy am 2026-11-23 geliefert. Urheber,
Stichprobe und Liga sind nicht angegeben. Eine Anmerkung in der Quelle („im Video als 1.08 versprochen“) deutet auf
eine Mitschrift aus einem Video hin. Die Quelle nennt 8 Positionen und 58 Kennzahlen, die Tabelle selbst listet 65.

**Status:** FM26-Werte, als feste Schwellen **nicht übernommen**. Die Rollenbewertung nutzt weiter Anker aus den
eigenen FM27-Daten (Perzentile 25/55/90, `scripts/rollen.py`). Aus der Quelle übernommen wurden nur zwei
Statistiken (siehe unten).

**Skala der Quelle:** „Elite“ = Zielwert für einen Kauf, „Cut-off“ = Ausschluss (kein Kauf). Richtwert der Quelle
für aussagekräftige Werte: mindestens 900 bis 1.200 Minuten bzw. 10 bis 15 Startelf-Einsätze.

## Abgleich mit FM27 (2026-11-23)

**Methode:** Für jede Schwelle das Perzentil im FM27-Pool der Positionsgruppe: Anteil der Spieler, die darunter
liegen (Gleichstände halb). Pool wie bei den Ankern: Stand 21.02.2027 (Kader + Spielersuche), Senior Team,
ab 900 Minuten, Ligen ab Stufe „Gut“, Positionsgruppen aus `config/rollen_kpis.yaml`. Werte pro 90 aus den Summen.

**Urteil:** „passt“ = Elite zwischen P80 und P97 **und** Cut-off zwischen P10 und P35 (entspricht ungefähr unseren
Ankern Gut = P90, Schlecht = P25). „unbrauchbar“ = Elite ab P99 oder bis P40, oder Cut-off ab P90 oder bis P3.
Alles andere „teilweise“ (meist ist der Cut-off zu streng und liegt nahe am Median).

**Ergebnis:** 10 von 56 prüfbaren Schwellen passen, 26 teilweise, 20 sind unbrauchbar. Auffällig:
- **Passquoten** liegen in FM27 viel höher (Median 88 bis 92 %): Elite-Schwellen der Quelle bei P2 bis P35,
  Cut-offs bei P0. Entweder hat FM27 eine andere Skala, oder die Quelle stimmt hier nicht.
- **IV Klärungen und Kopfballduelle pro 90:** Selbst der Cut-off liegt bei P98 bis P100, fast jeder IV fiele durch.
- **Torwart Save % minus xSave %:** Der Cut-off (−5) liegt bei P95; in FM27 liegt der Median bei −13.

| Position | Statistik | Elite | Cut-off | Perzentil Elite | Perzentil Cut-off | Median FM27 | P90 FM27 | Urteil |
|---|---|---|---|---|---|---|---|---|
| Torhüter | xGP / 90 | 0,15 | 0 | 77 | 53 | -0,02 | 0,22 | teilweise |
| Torhüter | Save % minus xSave % | 5 | -5 | 100 | 95 | -13 | -7,1 | unbrauchbar |
| Torhüter | Passquote % | 85 | 75 | 67 | 14 | 83 | 88,6 | teilweise |
| Torhüter | Paraden / 90 | 3,5 | 1,8 | 57 | 0 | 3,43 | 4,13 | unbrauchbar |
| Torhüter | Zu-null / 90 | 0,4 | 0,15 | 88 | 12 | 0,28 | 0,41 | passt |
| Innenverteidiger | Kopfballquote % | 72 | 65 | 68 | 33 | 68,57 | 77,97 | teilweise |
| Innenverteidiger | Kopfballduelle / 90 | 12 | 6 | 100 | 98 | 4,28 | 5,23 | unbrauchbar |
| Innenverteidiger | Tacklingquote % | 75 | 62 | 44 | 10 | 76,67 | 91,67 | teilweise |
| Innenverteidiger | Entsch. Tacklings / 90 | 0,5 | 0,15 | 100 | 76 | 0,09 | 0,2 | unbrauchbar |
| Innenverteidiger | Abgefangen / 90 | 4,5 | 2,5 | 98 | 2 | 3,31 | 4,01 | unbrauchbar |
| Innenverteidiger | Geblockt / 90 | 1,2 | 0,4 | 84 | 0 | 0,95 | 1,25 | unbrauchbar |
| Innenverteidiger | Klärungen / 90 | 6 | 3 | 100 | 100 | 1,48 | 1,98 | unbrauchbar |
| Innenverteidiger | Passquote % | 88 | 75 | 11 | 0 | 91,61 | 93,8 | unbrauchbar |
| Außenverteidiger | Flanken versucht / 90 | 5,5 | 2 | 78 | 54 | 1,85 | 7,11 | teilweise |
| Außenverteidiger | Flanken angek. / 90 | 1,5 | 0,7 | 97 | 77 | 0,25 | 1,13 | teilweise |
| Außenverteidiger | Flankenquote % | 25 | 15 | 89 | 59 | 13,47 | 25,16 | teilweise |
| Außenverteidiger | xA / 90 | 0,18 | 0,08 | 91 | 48 | 0,08 | 0,17 | teilweise |
| Außenverteidiger | Schlüsselpässe / 90 | 1,8 | 0,8 | 92 | 46 | 0,86 | 1,72 | teilweise |
| Außenverteidiger | Dribblings / 90 | 2,5 | 1 | 95 | 72 | 0,61 | 1,86 | teilweise |
| Außenverteidiger | Tacklingquote % | 75 | 62 | 40 | 6 | 77,55 | 90,6 | unbrauchbar |
| Außenverteidiger | Abgefangen / 90 | 3,5 | 1,8 | 50 | 1 | 3,5 | 4,2 | unbrauchbar |
| Außenverteidiger | Passquote % | 82 | 72 | 6 | 0 | 88,88 | 92,8 | unbrauchbar |
| Außenverteidiger | Distanz km / 90 | 12,5 | 10,8 | 75 | 23 | 12,11 | 12,94 | teilweise |
| Defensives Mittelfeld | Tacklingquote % | 75 | 62 | 49 | 12 | 75 | 86,43 | teilweise |
| Defensives Mittelfeld | Abgefangen / 90 | 4 | 2 | 96 | 4 | 3,13 | 3,78 | teilweise |
| Defensives Mittelfeld | Geblockt / 90 | 1,2 | 0,4 | 86 | 0 | 0,95 | 1,24 | unbrauchbar |
| Defensives Mittelfeld | Passquote % | 88 | 78 | 17 | 0 | 89,91 | 92,58 | unbrauchbar |
| Defensives Mittelfeld | Progressive Pässe / 90 | 5,5 | 2,8 | 64 | 3 | 4,97 | 6,58 | unbrauchbar |
| Defensives Mittelfeld | Distanz km / 90 | 13 | 11,2 | 98 | 13 | 12,23 | 12,67 | teilweise |
| Zentrales Mittelfeld | Pässe angek. / 90 | 60 | 40 | 92 | 17 | 50,83 | 58,82 | passt |
| Zentrales Mittelfeld | Passquote % | 88 | 78 | 35 | 0 | 89,14 | 92,21 | unbrauchbar |
| Zentrales Mittelfeld | Progressive Pässe / 90 | 5,5 | 3 | 72 | 15 | 4,48 | 6,44 | teilweise |
| Zentrales Mittelfeld | Schlüsselpässe / 90 | 2 | 0,8 | 87 | 25 | 1,15 | 2,17 | passt |
| Zentrales Mittelfeld | Großchancen / 90 | 1,5 | 0,5 | 100 | 78 | 0,32 | 0,67 | unbrauchbar |
| Zentrales Mittelfeld | xA / 90 | 0,18 | 0,06 | 73 | 16 | 0,12 | 0,26 | teilweise |
| Zentrales Mittelfeld | Distanz km / 90 | 13,5 | 11,5 | 100 | 12 | 12,29 | 12,78 | unbrauchbar |
| Offensives Mittelfeld | xA / 90 | 0,22 | 0,08 | 82 | 21 | 0,14 | 0,27 | passt |
| Offensives Mittelfeld | Entsch. Pässe (Spiel) / 90 | 1,8 | 0,6 | 82 | 6 | 1,25 | 1,97 | teilweise |
| Offensives Mittelfeld | Großchancen / 90 | 0,4 | 0,1 | 59 | 5 | 0,35 | 0,7 | teilweise |
| Offensives Mittelfeld | Progressive Pässe / 90 | 6 | 3,5 | 86 | 36 | 4,15 | 6,27 | teilweise |
| Offensives Mittelfeld | Dribblings / 90 | 2,5 | 1 | 83 | 61 | 0,62 | 3,43 | teilweise |
| Offensives Mittelfeld | Tore / 90 | 0,3 | 0,05 | 83 | 32 | 0,1 | 0,36 | passt |
| Offensives Mittelfeld | Passquote % | 82 | 72 | 2 | 0 | 87,62 | 91,41 | unbrauchbar |
| Flügelspieler | xA / 90 | 0,2 | 0,07 | 78 | 13 | 0,14 | 0,27 | teilweise |
| Flügelspieler | Schlüsselpässe / 90 | 2,2 | 1 | 84 | 13 | 1,63 | 2,46 | passt |
| Flügelspieler | Dribblings / 90 | 3 | 1,2 | 64 | 29 | 1,99 | 4,39 | teilweise |
| Flügelspieler | Flankenquote % | 25 | 15 | 93 | 44 | 15,58 | 23,75 | teilweise |
| Flügelspieler | Flanken angek. / 90 | 1,8 | 0,7 | 98 | 55 | 0,63 | 1,37 | teilweise |
| Flügelspieler | Großchancen / 90 | 0,35 | 0,08 | 51 | 3 | 0,34 | 0,69 | unbrauchbar |
| Flügelspieler | Tore / 90 | 0,35 | 0,1 | 82 | 30 | 0,19 | 0,44 | passt |
| Stürmer | npxG / 90 | 0,55 | 0,28 | 98 | 46 | 0,29 | 0,46 | teilweise |
| Stürmer | xG pro Schuss | 0,16 | 0,09 | 85 | 16 | 0,12 | 0,17 | passt |
| Stürmer | Schüsse / 90 | 3,5 | 1,8 | 92 | 20 | 2,37 | 3,4 | passt |
| Stürmer | Tore / 90 | 0,65 | 0,3 | 93 | 34 | 0,38 | 0,62 | passt |
| Stürmer | Chancenverwertung % | 20 | 13 | 76 | 38 | 15,49 | 24,56 | teilweise |
| Stürmer | Schussgenauigkeit % | 45 | 35 | 18 | 3 | 52,63 | 63,78 | unbrauchbar |

**Nicht prüfbar (9):** Saisonwerte (Torhüter xGP absolut, Zu-null-Spiele je Saison, gehaltene Elfmeter;
Fehler vor Gegentor bei IV und AV) sowie Ballgewinne (DM, ZM, ST) und Ballverluste (ZM): Die gibt es nur live,
nicht im Export.

## Was übernommen wurde

Nur die **Auswahl** von Statistiken, nicht die Schwellen. Geprüft wurde, welche Statistiken der Quelle unsere
Rollenbewertung noch nicht nutzt und ob sie in FM27 trennscharf sind (Anker P25 < P55 < P90 im Pool):

| Statistik | Prüfung FM27 (P25 / P55 / P90 pro 90) | Entscheidung |
|---|---|---|
| Entscheidende Tacklings (`tacklings_entscheidend`) | IV 0,048 / 0,101 / 0,201; DM 0 / 0,051 / 0,132; AV 0 / 0,066 / 0,154 | in Baustein Zweikampf (alle Rollen mit Zweikampf) |
| xG pro Schuss (`xg_pro_schuss_avg`) | ST 0,11 / 0,12 / 0,17 | neuer Baustein Abschlussqualität: Mittelstürmer und Knipser je Gewicht 1 |
| Fehler vor Gegentor (`fehler_torfolge`) | 88 % der IV, 96 % der DM, 59 % der TW mit 0; P25 = P55 = 0 | verworfen: nicht trennscharf |
| Kopfballduelle pro 90, Schüsse pro 90, Schlüsselpässe pro 90 | – | verworfen: doppelt zu Luftkampf (gewonnene Kopfballduelle), Torgefahr (Schüsse aufs Tor) und Chancenkreation (entscheidende Pässe aus dem Spiel) |
| Zu-null-Spiele, gehaltene Elfmeter | – | verworfen: teamabhängig bzw. Saisonwert |

Beide übernommenen Statistiken liefert auch die Live-Quelle (`K Tck/90`, `xG/shot` in `config/live_spalten.yaml`).
Details und Änderungsdatum in [rollen-kpis.md](rollen-kpis.md).
