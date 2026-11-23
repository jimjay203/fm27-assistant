# Erfolgsmessung je Rolle: welche Statistiken passen? (Vorschlag, ungeprüft)

**Herleitung:** Claude am 2026-11-22 (Auftrag Jimmy) aus den Rollenbeschreibungen in [rollen.md](rollen.md)
(Quelle Zweierkette, aus FM26, für FM27 ungeprüft) und den Statistiken, die der Reader liefert. Maschinenlesbar:
`config/rollen_kpis.yaml` (diese Datei wird daraus erzeugt). **Nichts davon ist an FM27 validiert**, es sind begründete
Setzungen zur Prüfung durch Jimmy.

**So wird gerechnet:** Jede Rolle ist eine gewichtete Mischung aus *Bausteinen* (Gewicht 3 = Kern, 2 = wichtig,
1 = Nebenaspekt). Ein Baustein ist der Durchschnitt seiner Statistik-Scores. Ein Statistik-Score läuft von 0 bis 100 und
bezieht sich auf die Verteilung der Spieler auf derselben Position (Perzentile, siehe `anker_fm27.yaml`).
Der Spieler wird mit **beiden** seiner Rollen bewertet (mit Ball und ohne Ball).

**Änderungen:** 2026-11-23 (Auftrag Jimmy): Baustein Zweikampf um entscheidende Tacklings ergänzt, neuer Baustein
Abschlussqualität (xG pro Schuss) für Mittelstürmer und Knipser. Anregung aus den FM26-Moneyball-Benchmarks, Abgleich
und verworfene Kandidaten in [benchmarks-fm26.md](benchmarks-fm26.md).

**Grundsätzliche Datenlücken (für alle Rollen):** Positionsspiel und Laufwege ohne Ball, Passlänge und -risiko,
Ablagen, Kontertore, Zielzonen von Flanken. Defensivwerte hängen vom Teamstil ab (Topclubs haben viel Ballbesitz).

## Bausteine
| Baustein | Statistiken (↓ = niedriger ist besser) |
|---|---|
| torgefahr (Torgefahr) | npxg, schuesse_aufs_tor, konversionsrate_pct |
| abschlussqualitaet (Abschlussqualität (xG pro Schuss), ergänzt 2026-11-23) | xg_pro_schuss_avg |
| fernschuss (Schüsse von außerhalb des Strafraums) | schuesse_fern_p90 |
| chancen (Chancenkreation) | xa, entscheidende_paesse_spiel_p90, grosschancen |
| ballvortrag (Ballvortrag (Pässe nach vorn und Dribblings)) | progressive_paesse, dribblings |
| dribbling (Dribbling) | dribblings |
| aufbau (Spielaufbau (Fortschritt und Volumen)) | progressive_paesse, paesse_angekommen |
| passsicherheit (Passsicherheit) | passquote_pct, ballverluste ↓ |
| flanken (Flanken aus dem Spiel) | flanken_spiel_angekommen, flankenquote_spiel_pct |
| luftkampf (Luftkampf) | kopfbaelle_gewonnen, kopfballduelle_gewonnen_pct |
| tempo (Sprinthäufigkeit (Näherung für Tempo, nicht Schnelligkeit)) | sprints_p90 |
| laufleistung (Laufleistung) | distanz_km |
| zweikampf (Zweikampf) | tacklings_gewonnen, tackling_pct, tacklings_entscheidend (ergänzt 2026-11-23) |
| abfangen (Abfangen) | abgefangen |
| raumsicherung (Raumsicherung (Klären, Blocken)) | klaerungen, geblockt, schuesse_geblockt |
| pressing (Pressing) | pressing_erfolgreich, pressingquote_pct |
| ballgewinn (Ballgewinne) | ballgewinne |
| disziplin (Disziplin (wenige Fouls)) | fouls ↓ |
| tw_schussabwehr (Torwart - Schussabwehr) | xgp, par_pct, xsv_pct, gegentore_n ↓ |
| tw_aufbau (Torwart - Spielaufbau) | passquote_pct, progressive_paesse, paesse_angekommen |
| tw_klaerung (Torwart - Aktionen außerhalb der Linie (schwach belegt)) | klaerungen, abgefangen |

## Torwart

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Torwart | Standard | tw_schussabwehr 3, tw_aufbau 1 | Ausgewogene Standardrolle: im Kern zählt das Halten. Verteilung hängt laut Quelle von der Spielanlage ab, daher nur schwach gewichtet. | mittel | Herauslaufen und Strafraumbeherrschung sind nicht erfasst. xGP am 2026-11-22 an Hein gegen die Spielansicht geprüft (stimmt nach Korrektur im Fork); xSv % weicht dort um etwa 1 Punkt ab. |
| Linientorhüter | ohne Ball | tw_schussabwehr 3 | Bleibt im Tor, Mitspieler schützen den Raum davor: Erfolg ist, Schüsse zu halten. | mittel | Torlinienpositionierung nicht erfasst. xGP geprüft (Hein, 2026-11-22), xSv % weicht um etwa 1 Punkt ab. |
| Libero-Torhüter | ohne Ball | tw_schussabwehr 2, tw_klaerung 1 | Verteidigt aktiv außerhalb des Tores, fängt Pässe ab, stellt Stürmer im Eins-gegen-Eins. | **gering** | Herauslaufen und Sweeper-Aktionen sind nicht erfasst; Abfangen/Klären ist bei Torhütern meist 0 (Anker nicht trennscharf). |
| Kompromissloser Torhüter | mit Ball | passsicherheit 1 | Vermeidet jedes Risiko, schlägt lang. Messbar ist nur, dass er den Ball nicht verliert. | **gering** | Lange Abschläge und deren Ergebnis fehlen; Passquote würde diese Rolle zu Unrecht bestrafen und ist deshalb weggelassen. |
| Ballspielender Torhüter | mit Ball | tw_aufbau 3, passsicherheit 1 | Aktiv im Aufbau, überspielt das Pressing als zusätzlicher Feldspieler: Passquote, Fortschritt und wenig Ballverluste. | mittel |  |

## Innenverteidigung

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Innenverteidiger | Standard | raumsicherung 2, luftkampf 2, zweikampf 1, abfangen 1, passsicherheit 1, aufbau 1 | Standardrolle: Tor schützen, auf Ballverluste reagieren, in offensiven Taktiken die Zirkulation stützen. | mittel |  |
| Stoppender Innenverteidiger | ohne Ball | zweikampf 3, ballgewinn 2, abfangen 1, luftkampf 1, disziplin 1 | Verteidigt nach vorne, sucht frühe Zweikämpfe: Zweikämpfe und Ballgewinne zählen am meisten, Fouls kosten. | mittel | Ob die Zweikämpfe früh (hoch) stattfinden, ist nicht erfasst. |
| Absichernder Innenverteidiger | ohne Ball | raumsicherung 3, abfangen 2, luftkampf 2, disziplin 1 | Zurückhaltend, hält die Linie, wartet ab: Klären, Blocken, Abfangen und Kopfbälle statt aktiver Zweikämpfe. | mittel | Linienhöhe und Staffelung nicht erfasst. |
| Ballspielender Innenverteidiger | mit Ball | aufbau 3, passsicherheit 2, dribbling 1 | Mehr Risiko im Aufbau, Steckpässe aus der Tiefe, Läufe mit Ball: progressive Pässe, Passvolumen, Dribblings bei vertretbaren Ballverlusten. | mittel | Steckpässe sind nur über 'progressive Pässe' angenähert. |
| Kompromissloser Innenverteidiger | mit Ball | passsicherheit 3, luftkampf 1 | Safety first: Sicherheitspässe und lang unter Druck. Messbar ist die Sicherheit (Passquote, wenig Ballverluste). | **gering** | Lange Bälle unter Druck und ihr Ergebnis fehlen. |
| Aufrückender Innenverteidiger | mit Ball | aufbau 2, dribbling 1, fernschuss 1, passsicherheit 1 | Rückt ins Mittelfeld auf, unterstützt mit Pässen, gelegentlich Torgefahr aus der zweiten Reihe. | **gering** | Aufrücken selbst nicht erfasst. Torgefahr nur über Fernschüsse. Quelle nennt außergewöhnliche technische und mentale Fähigkeiten. |
| Halbraumverteidiger | Standard | zweikampf 1, raumsicherung 1, abfangen 1, luftkampf 1, aufbau 1 | Seitlicher Spieler der Dreierkette: Verteidigen wie ein IV, in Ballbesitz sichere Anspielstation in der Tiefe. | mittel |  |
| Stoppender Halbraumverteidiger | ohne Ball | zweikampf 3, ballgewinn 2, abfangen 1, luftkampf 1, disziplin 1 | Quelle: textgleich mit dem Stoppenden Innenverteidiger. | mittel |  |
| Absichernder Halbraumverteidiger | ohne Ball | raumsicherung 3, abfangen 2, luftkampf 2, disziplin 1 | Quelle: textgleich mit dem Absichernden Innenverteidiger. | mittel |  |
| Hinterlaufender Halbraumverteidiger | mit Ball | flanken 2, ballvortrag 1, chancen 1, laufleistung 1, tempo 1 | Wird mit Ball zum Flügelläufer, hinterläuft Mitspieler, flankt im letzten Drittel. | **gering** | Hinterlaufen selbst nicht erfasst; Flanken und Laufleistung sind Näherungen. |

## Außen-/Flügelverteidiger

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Außenverteidiger | Standard | zweikampf 2, abfangen 1, flanken 1, aufbau 1 | Hauptsächlich Defensivspieler, schaltet sich bei Bedarf nach vorne ein. | mittel |  |
| Flügelverteidiger | Standard | flanken 2, zweikampf 1, aufbau 1, laufleistung 1, chancen 1 | Kreuzung aus AV und Flügelspieler: Breite, Anspielstation im Aufbau, Läufe und Flanken im letzten Drittel. | mittel |  |
| Abwartender Außenverteidiger | ohne Ball | abfangen 2, zweikampf 2, raumsicherung 1, disziplin 1 | Bleibt tief, sichert gegen Konter ab, Mitspieler pressen: Abfangen und Zweikämpfe ohne Fouls. | mittel |  |
| Pressender Außenverteidiger | ohne Ball | pressing 3, zweikampf 2, ballgewinn 1 | Läuft gegnerische Außen früh und hoch an: Pressing, Zweikämpfe, Ballgewinne. | mittel |  |
| Inverser Außenverteidiger | mit Ball | aufbau 3, passsicherheit 2 | Wird mit Ball zum zusätzlichen Innenverteidiger/Absicherer und rückt nach innen: Passsicherheit und Spielaufbau. | **gering** | Einrücken und Konterabsicherung (Positionsspiel) nicht erfasst. |
| Abwartender Flügelverteidiger | ohne Ball | abfangen 2, zweikampf 2, raumsicherung 1, disziplin 1 | Quelle: textgleich mit dem Abwartenden Außenverteidiger. | mittel |  |
| Pressender Flügelverteidiger | ohne Ball | pressing 3, zweikampf 2, ballgewinn 1 | Quelle: textgleich mit dem Pressenden Außenverteidiger. | mittel |  |
| Inverser Flügelverteidiger | mit Ball | aufbau 3, passsicherheit 2 | Rückt in die Mitte, unterstützt das Passspiel, verhält sich wie ein defensiver Mittelfeldspieler; seltener Flanken und Hinterlaufen. | **gering** | Einrücken nicht erfasst. |
| Spielmachender Flügelverteidiger | mit Ball | chancen 3, aufbau 2, flanken 1 | Zentral, Schlüsselrolle im Passspiel, soll Chancen kreieren (tödliche Pässe, Flanken). | mittel | Quelle nennt technische Fähigkeiten als Voraussetzung. |
| Vorgeschobener Flügelverteidiger | mit Ball | flanken 3, laufleistung 2, dribbling 2, chancen 1, tempo 1 | Spielt so hoch wie möglich, gibt Breite, unterstützt mit Läufen im letzten Drittel. | mittel |  |

## Defensives Mittelfeld

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Defensiver Mittelfeldspieler | Standard | zweikampf 2, abfangen 2, passsicherheit 2, ballgewinn 1, raumsicherung 1 | Schützt die Abwehr und den Raum davor, Bindeglied mit einfachen Pässen. | mittel |  |
| Halbverteidiger | ohne Ball | raumsicherung 2, abfangen 2, zweikampf 1, luftkampf 1 | Lässt sich in die Abwehrkette fallen und agiert als zusätzlicher IV, sonst wie ein Sechser. | **gering** | Zurückfallen (Positionsspiel) nicht erfasst. |
| Abschirmender Sechser | ohne Ball | abfangen 3, raumsicherung 2, zweikampf 1, disziplin 1 | Hält die Position, stellt Passwege zu, presst selten: Abfangen und Blocken statt aktiver Zweikämpfe. | mittel | Passwege zustellen ist nicht erfasst. |
| Pressender Sechser | ohne Ball | pressing 3, zweikampf 2, ballgewinn 2 | Verlässt die Position für das hohe Pressing, höhere Grundposition. | mittel |  |
| Flügelsichernder Sechser | ohne Ball | zweikampf 2, abfangen 2, laufleistung 1, ballgewinn 1 | Sichert weite Bereiche, doppelt mit dem Außenverteidiger: Zweikämpfe, Abfangen, Laufarbeit. | **gering** | Doppeln und Seitenwechsel der Position nicht erfasst. |
| Tiefer Spielmacher | mit Ball | aufbau 3, passsicherheit 2, chancen 1 | Leitet Angriffe aus der Tiefe mit gezielten Pässen ein; kreativ, aber oft tiefster Mittelfeldspieler. | mittel |  |
| Abkippender Sechser | mit Ball | passsicherheit 3, aufbau 2 | Fällt im Aufbau in die Abwehrkette, erhöht die Pressingresistenz: sichere Pässe, kaum Ballverluste. | **gering** | Abkippen selbst nicht erfasst. |
| Box-to-Box-Spieler | mit Ball | laufleistung 2, torgefahr 2, ballvortrag 1, chancen 1, aufbau 1 | Dynamik in Aufbau und letztem Drittel, kommt spät in den Strafraum (zweite Bälle, Flanken). Quelle: außergewöhnliche Physis und Einsatzfreude. | mittel | Späte Läufe in den Strafraum nicht erfasst. |
| Box-to-Box-Spielmacher | mit Ball | chancen 2, aufbau 2, laufleistung 2 | Kreatives Herz, verbindet Mannschaftsteile, vereint Tiefen und Vorgeschobenen Spielmacher; braucht Spielmacherqualität und Physis. | mittel |  |

## Zentrales Mittelfeld

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Zentraler Mittelfeldspieler | Standard | aufbau 1, chancen 1, zweikampf 1, abfangen 1, passsicherheit 1, laufleistung 1 | Vielseitiges Scharnier, muss alles erfüllen: gleichmäßige Mischung. | mittel |  |
| Abschirmender Achter | ohne Ball | abfangen 3, zweikampf 1, raumsicherung 1 | Hält die Position, stellt Passwege zu, verstellt den Weg durch die Mitte. | mittel | Passwege zustellen nicht erfasst. |
| Pressender Achter | ohne Ball | pressing 3, zweikampf 2, ballgewinn 2 | Quelle: textgleich mit dem Pressenden Sechser. | mittel |  |
| Flügelsichernder Achter | ohne Ball | zweikampf 2, abfangen 2, laufleistung 1, ballgewinn 1 | Quelle: textgleich mit dem Flügelsichernden Sechser. | **gering** | Doppeln mit dem Außenverteidiger und Seitenwechsel der Position nicht erfasst. |
| Spielmacher | mit Ball | chancen 2, aufbau 2, passsicherheit 1 | Kreative Verbindung, bringt den Ball in gefährliche Zonen, Steckpässe auf Offensive. | mittel |  |
| Weiter Achter | mit Ball | aufbau 2, laufleistung 2, passsicherheit 1 | Breiter Verbinder mit Laufstärke, gute Option für Diagonalbälle und Seitenwechsel. | **gering** | Diagonalbälle und Seitenwechsel (Passlänge) nicht erfasst. |
| Vorgeschobener Spielmacher | mit Ball | chancen 3, aufbau 2, passsicherheit 1 | Orchestriert zwischen den Linien des Gegners, schafft Torchancen mit tödlichen Pässen ins letzte Drittel. | mittel |  |

## Offensives Mittelfeld

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Offensiver Mittelfeldspieler | Standard | chancen 2, dribbling 1, torgefahr 1, passsicherheit 1 | Zwischen den Linien, braucht Passspiel, Dribbling und Abschluss; Chancen für sich und andere. | mittel |  |
| Mitarbeitender Zehner | ohne Ball | pressing 2, abfangen 1, zweikampf 1, ballgewinn 1, laufleistung 1 | Lässt sich fallen, hilft, das Zentrum zu sichern. | mittel |  |
| Zentraler Umschaltzehner | ohne Ball | torgefahr 2, tempo 1, dribbling 1, chancen 1 | Arbeitet nicht nach hinten, ist nach Ballgewinn Anspielstation für Konter: Erfolg ist die Wirkung im Umschalten, nicht die Defensive. | **gering** | Konterwirkung nicht direkt messbar (keine Kontertore/-chancen). Defensive Beiträge werden bewusst nicht verlangt. |
| Ausweichender Umschaltzehner | ohne Ball | tempo 2, torgefahr 1, dribbling 1, chancen 1 | Höhere Position, weicht in die Halbräume aus für Konter über außen. | **gering** | Konterwirkung nicht direkt messbar. |
| Freigeist | mit Ball | chancen 2, dribbling 2, torgefahr 1 | Totale kreative Freiheit, geht am Ball jedes Risiko ein: Chancenkreation und Dribbling; Ballverluste werden nicht bestraft. | **gering** | Freiheit/Unberechenbarkeit nicht messbar. |
| Halbraumspieler | mit Ball | chancen 2, flanken 1, torgefahr 1, laufleistung 1 | Bewegt sich weit, kombiniert mit Außenstürmern, läuft durch Schnittstellen, flankt oder läuft vor. | **gering** | Läufe durch Schnittstellen nicht erfasst. |
| Zweiter Stürmer | mit Ball | torgefahr 3, chancen 1, dribbling 1 | Sorgt vor allem für Torgefahr, rückt im letzten Drittel in die vorderste Reihe. | mittel |  |

## Flügel

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Äußerer Mittelfeldspieler | Standard | chancen 1, flanken 1, aufbau 1, passsicherheit 1, laufleistung 1 | 'ZM für außen': frühe Flanken und Pässe aus der Tiefe, Technik statt Tempo und Dribbling. | mittel |  |
| Flügelspieler | Standard | dribbling 2, flanken 2, chancen 1, tempo 1 | Breite, Flanken und Pässe von der Seitenlinie, Eins-gegen-Eins per Dribbling. Quelle nennt Dribbling als Attribut. | mittel |  |
| Mitarbeitender Außenspieler | ohne Ball | laufleistung 2, zweikampf 1, abfangen 1, pressing 1, ballgewinn 1 | Macht seine Seite dicht, fällt zeitweise in die letzte Linie: Laufarbeit und Defensivaktionen. | mittel |  |
| Mitarbeitender Flügelspieler | ohne Ball | laufleistung 2, zweikampf 1, abfangen 1, pressing 1, ballgewinn 1 | Quelle: textgleich mit dem Mitarbeitenden Außenspieler. | mittel |  |
| Äußerer Umschaltspieler | ohne Ball | tempo 2, dribbling 1, chancen 1, flanken 1 | Hält eine hohe Position, ist nach Ballgewinn anspielbar: Erfolg ist die Wirkung im Umschalten (Tempo, Dribbling, Vorlagen). | **gering** | Konterwirkung nicht direkt messbar. Defensive Beiträge werden bewusst nicht verlangt (Quelle: Seite kann Schwachstelle werden). |
| Umschaltflügelspieler | ohne Ball | tempo 2, dribbling 1, chancen 1, flanken 1 | Quelle: textgleich mit dem Äußeren Umschaltspieler. | **gering** | Konterwirkung nicht direkt messbar. |
| Inverser Umschaltflügelspieler | ohne Ball | tempo 2, torgefahr 1, dribbling 1, chancen 1 | Zieht beim gegnerischen Angriff nach innen, Konter über die Halbräume, anspielbar für vertikale Bälle. | **gering** | Konterwirkung nicht direkt messbar. |
| Halbraumflügel | mit Ball | chancen 2, torgefahr 1, flanken 1, dribbling 1 | Rückt in die Halbräume, öffnet Räume für Hinterlaufende, spielt Pässe und Flanken in den Strafraum, näher am Tor als ein klassischer Flügel. | mittel |  |
| Äußerer Spielmacher | mit Ball | chancen 3, aufbau 2, dribbling 1 | Startet außen, übernimmt dann im Zentrum die kreative Hauptrolle, tödliche Bälle aus den Halbräumen. | mittel |  |
| Inverser Außenstürmer | mit Ball | torgefahr 3, dribbling 1, tempo 1, chancen 1 | Rückt in die Halbräume, Läufe in den Rücken der Abwehr, Torgefahr von außen. | mittel |  |
| Außenstürmer | mit Ball | torgefahr 3, dribbling 2, tempo 1 | Gibt Breite, zieht in den Strafraum und in den Rücken der Abwehr, Torgefahr; in erster Linie offensiv. | mittel |  |

## Stürmer

| Rolle | Phase | Bausteine (Gewicht) | Begründung | Zuverlässigkeit | Lücken |
|---|---|---|---|---|---|
| Mittelstürmer | Standard | torgefahr 3, abschlussqualitaet 1, chancen 1, luftkampf 1 | Klassische Nummer neun: Angriffe abschließen, selbst oder durch überlegtes Ablegen. | mittel |  |
| Mitarbeitender Mittelstürmer | ohne Ball | pressing 2, zweikampf 1, ballgewinn 1, laufleistung 1 | Positioniert sich tiefer, hilft, das Zentrum abzusichern. | mittel |  |
| Zentraler Umschaltstürmer | ohne Ball | torgefahr 2, tempo 1, dribbling 1 | Arbeitet nicht nach hinten, ist nach Ballgewinn Anspielstation für Konter. | **gering** | Konterwirkung nicht direkt messbar. Defensive Beiträge werden bewusst nicht verlangt. |
| Ausweichender Umschaltstürmer | ohne Ball | tempo 2, torgefahr 2, dribbling 1 | Höhere Position, weicht in die Halbräume für Konter über außen aus. | **gering** | Konterwirkung nicht direkt messbar. |
| Hängende Spitze | mit Ball | chancen 3, aufbau 1, passsicherheit 1 | Verbindet Mittelfeld und Angriff, nimmt Pässe zwischen den Linien an, verteilt auf Nachrückende und Außen. | mittel |  |
| Falsche Neun | mit Ball | chancen 2, dribbling 1, aufbau 1, torgefahr 1 | Fällt in den Zehnerraum, agiert wie ein vorgeschobener Spielmacher, bindet Verteidiger. | **gering** | Zurückfallen und das Binden von Verteidigern nicht erfasst. |
| Zielspieler | mit Ball | luftkampf 3, torgefahr 2, chancen 1 | Physis und Größe, Abnehmer langer Bälle (festmachen, weiterleiten), Lufthoheit im Strafraum. Quelle: Physis und Größe als Attribute. | mittel | Festmachen und Weiterleiten (Ablagen) nicht erfasst, nur Kopfbälle und xAssists. |
| Knipser | mit Ball | torgefahr 3, abschlussqualitaet 1 | Lauert auf der Höhe des letzten Verteidigers, wenig Aufbau: Erfolg sind Torgefahr und Verwertung, gute Abschlusspositionen (xG pro Schuss). Quelle: gute Fähigkeiten ohne Ball. | mittel | Antizipation und Laufwege ohne Ball nicht erfasst. |
| Halbraumstürmer | mit Ball | torgefahr 2, tempo 1, dribbling 1 | Läuft ständig die Zwischenräume an, anspielbar in den Fuß oder in die Tiefe. | **gering** | Laufwege nicht erfasst. |

## Zusammenfassung
- 68 Rollen, davon 23 mit Zuverlässigkeit **gering** (die entscheidenden Merkmale fehlen in den Daten).
- Rollen mit **gering** liefern nur eine grobe Näherung und sollten nicht allein über Kauf oder Verkauf entscheiden.
