# Benchmarks „What does Good look like in FM24?“ (aus FM24, für FM27 ungeprüft)

**Quelle:** Grafik „What does “Good” look like in FM24?“ von FM Stag („CM and FM since 1997“), von Jimmy am
2026-11-22 als Grundlage für Rollenprofile geliefert. Von Claude per Hand aus dem Bild abgetippt. **Bitte
gegenlesen**, bevor Entscheidungen auf diesen Zahlen beruhen.

**Status:** FM24-Werte. Ob FM27 dieselbe Skala hat (gleiche Zähllogik, gleiche Spielstärke-Verteilung), ist
**nicht belegt**. `scripts/benchmark.py` prüft das an euren Live-Daten (Verteilung der Werte je Stat) und
meldet Abweichungen. Gut/OK/Schlecht ist die Einstufung der Quelle, nicht von uns. Wie sie entstanden ist
(Stichprobe, Liga, Position), steht nicht in der Grafik.

Alle Werte pro 90 Minuten, außer `%`. „Schlecht“ und „Gut“ sind Referenzpunkte, keine Grenzen: Werte
darüber oder darunter kommen vor.

| Rollentyp | Statistik | Gut | OK | Schlecht |
|---|---|---|---|---|
| **Torwart** | xGoals verhindert / 90 | 0,25 | 0 | −0,38 |
| | Gegentore / 90 (niedriger ist besser) | 0,75 | 1,41 | 2,15 |
| | Abgefangene Bälle / 90 | 0,22 | 0,1 | 0,04 |
| | Passquote % | 97 | 78 | 47 |
| **Innenverteidiger – Stopper** | Tacklings / 90 | 2,38 | 1,29 | 0,8 |
| | Kopfballquote % | 82 | 72 | 59 |
| | Klärungen / 90 | 1,64 | 0,85 | 0,44 |
| | Abgefangene Bälle / 90 | 3,18 | 2,15 | 1,36 |
| | Geblockte Schüsse / 90 | 0,72 | 0,42 | 0,19 |
| **Innenverteidiger – Spielaufbau** | Tacklings / 90 | 2,36 | 1,24 | 0,88 |
| | Klärungen / 90 | 0,89 | 0,64 | 0,39 |
| | Abgefangene Bälle / 90 | 3 | 2,33 | 1,69 |
| | Geblockte Schüsse / 90 | 0,63 | 0,34 | 0,16 |
| | Progressive Pässe / 90 | 6,9 | 4,52 | 3,17 |
| **Außenverteidiger** | Tacklings / 90 | 3,66 | 2,75 | 1,44 |
| | Abgefangene Bälle / 90 | 3,31 | 2,75 | 2 |
| | Erfolgreiche Pressings / 90 | 3,5 | 2,48 | 1,35 |
| | Flanken aus dem Spiel angekommen / 90 | 0,47 | 0,14 | 0,03 |
| | Progressive Pässe / 90 | 8,59 | 6,13 | 4,14 |
| **Wing-Back** | Tacklings / 90 | 3,88 | 2,89 | 1,57 |
| | Abgefangene Bälle / 90 | 3,48 | 2,78 | 1,89 |
| | Erfolgreiche Pressings / 90 | 3,64 | 2,79 | 1,51 |
| | Flanken aus dem Spiel angekommen / 90 | 0,71 | 0,25 | 0,04 |
| | Dribblings / 90 | 3,03 | 1,69 | 0,39 |
| **Mittelfeld – Zerstörer** | Tacklings / 90 | 3,01 | 2,16 | 1,17 |
| | Abgefangene Bälle / 90 | 2,75 | 1,97 | 1,32 |
| | Blocks / 90 | 0,75 | 0,41 | 0,2 |
| | Erfolgreiche Pressings / 90 | 3,81 | 2,84 | 1,13 |
| | Passquote % | 94 | 90 | 86 |
| **Mittelfeld – Spielmacher** | Schlüsselpässe aus dem Spiel / 90 | 1,82 | 1,23 | 0,76 |
| | Progressive Pässe / 90 | 7,19 | 4,86 | 2,67 |
| | xAssists / 90 | 0,33 | 0,19 | 0,1 |
| | Dribblings / 90 | 2,5 | 1,32 | 0,43 |
| | Passquote % | 91 | 88 | 82 |
| **Offensives Mittelfeld** | Schlüsselpässe aus dem Spiel / 90 | 1,81 | 1,27 | 0,75 |
| | xAssists / 90 | 0,32 | 0,21 | 0,13 |
| | Dribblings / 90 | 3,7 | 1,85 | 0,89 |
| | Passquote % | 88 | 85 | 82 |
| | Schüsse aufs Tor / 90 | 1,1 | 0,71 | 0,37 |
| **Flügel – Vorlagengeber** | Dribblings / 90 | 4,69 | 2,4 | 1,05 |
| | Flanken aus dem Spiel angekommen / 90 | 0,66 | 0,33 | 0,1 |
| | Sprints / 90 | 18,03 | 14,19 | 8,57 |
| | Schlüsselpässe aus dem Spiel / 90 | 1,94 | 1,15 | 0,59 |
| | xAssists / 90 | 0,36 | 0,19 | 0,1 |
| **Flügel – Stürmer** | Dribblings / 90 | 4,6 | 3,01 | 1,5 |
| | Schüsse aufs Tor / 90 | 1,34 | 0,82 | 0,43 |
| | Sprints / 90 | 17,49 | 14,17 | 8,24 |
| | Non-Penalty-xG / 90 | 0,44 | 0,25 | 0,15 |
| | Konversionsrate % | 28 | 16 | 7 |
| **Stürmer – Vorlagengeber** | Gewonnene Kopfbälle / 90 | 3,98 | 1,95 | 0,67 |
| | xAssists / 90 | 0,25 | 0,14 | 0,08 |
| | Non-Penalty-xG / 90 | 0,52 | 0,3 | 0,21 |
| | Schüsse aufs Tor / 90 | 1,51 | 0,94 | 0,64 |
| | Konversionsrate % | 30 | 20 | 13 |
| **Stürmer – Torjäger** | Gewonnene Kopfbälle / 90 | 5,08 | 2,76 | 1,03 |
| | Dribblings / 90 | 3,05 | 1,17 | 0,69 |
| | Non-Penalty-xG / 90 | 0,5 | 0,35 | 0,22 |
| | Schüsse aufs Tor / 90 | 1,57 | 1,09 | 0,73 |
| | Konversionsrate % | 30 | 21 | 15 |

## Hinweise zur Übertragung auf FM27
- Welche Zählweise die Quelle für „Tacklings“ und „Erfolgreiche Pressings“ nutzt, steht nicht in der Grafik.
  Wir nehmen **gewonnene Tacklings** und **erfolgreiche Pressings** (ungeprüft).
- „Konversionsrate“ = Tore / Schüsse. Ob die Quelle Elfmeter einrechnet, ist offen; wir rechnen alle Tore und Schüsse.
- Die Rollentypen der Quelle (z. B. „Spielmacher“) sind nicht dieselben wie die Rollen in `taktik.md`
  („Zwischenraumspieler“, „Umschaltflügelspieler“). Die Zuordnung ist eine Entscheidung von Jimmy.
- Defensive Werte hängen vom Teamstil ab (Ballbesitz, Pressinghöhe). Dafür gibt es keine Bereinigung.
