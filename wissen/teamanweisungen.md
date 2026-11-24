# Teamanweisungen FM27 (UI-Katalog)

Quelle: Screenshots aus dem FM27-UI (Save werder, 03.07.2027, Taktik 4-2-3-1). Stufen in UI-Reihenfolge,
Texte gekürzt aus den UI-Beschreibungen und dem "Mitarbeiter-Feedback". Das sind Aussagen des Spiels,
keine Match-Engine-Tests. Fett = Ist-Stand Werder, 03.07.2027.

# Mit Ball

## Gruppen im UI
| Gruppe (UI) | Anweisungen |
|---|---|
| Übersicht | Passspiel, Tempo, Angriffsbreite, Offensives Umschalten, Kreative Freiheit, Zeitspiel, Standards rausholen |
| Letztes Drittel | Dribbling, Geduld, Fernschüsse, Flankenstil |
| Mittleres Drittel | Unterstützende Läufe, Dribbling, Aufbauspiel, Pass-Aufnahme |
| Aufbau | Spielaufbau-Strategie, Abstöße, Spielaufbau TW (Geschwindigkeit), Spielaufbau TW (Ziel) |

## Stufen und Wirkung laut UI
| Anweisung | Stufen | Wirkung laut UI (Plus / Minus) |
|---|---|---|
| Passspiel | Viel kürzer · Kürzer · **Standard** · Vertikaler · Viel vertikaler | Kürzer: "Angriffe geduldiger aufbauen", hält den Ball. Standard: weniger Ballbesitz als kürzer, langsamerer Aufbau als vertikaler. Viel vertikaler: "Gegnerische Verteidigung pressen" |
| Tempo | Viel geringer · Geringer · **Standard** · Höher · Viel höher | Geringer: geduldiger, mehr Zeit am Ball. Standard: weniger Ballbesitz als viel langsameres Tempo |
| Angriffsbreite | Viel enger · Enger · **Standard** · Breiter · Viel breiter | Enger: Zentrale besetzen, nähere Anspielstationen. Breiter: "Spiel breit machen, Abstand zwischen den Spielern". Standard: Gegner "nicht so stark auseinandergezogen wie mit breiterem Ansatz" |
| Offensives Umschalten | Formation halten · **Standard** · Konter | Formation halten: seltener Konter, Ballbesitzsicherung priorisieren. Konter: häufiger Konter |
| Kreative Freiheit | Disziplinierter spielen · **Ausgewogen** · Kreativer spielen | Kreativer: mehr Freiraum, "Position verlassen" |
| Zeitspiel | **Seltener** · Standard · Häufiger | Seltener: Ball möglichst lange im Spiel |
| Standards rausholen | Ball im Spiel halten · **Standards rausholen** | Standards rausholen: mehr offensive Standards, Kopfballspezialisten nach vorn; Minus: "kommt seltener zu Torchancen aus dem Spiel heraus". Ball im Spiel halten: Chancen aus dem Spiel kreieren |
| Dribbling | Seltener · **Ausgewogen** · Häufiger | Seltener: auf Passkombinationen fokussieren. Häufiger: Verteidigung ausdribbeln |
| Geduld | Flanken früh schlagen · **Standard** · Geduldig spielen | Geduldig: "geduldig im letzten Drittel, generiert hochkarätige Chancen". Früh: viele Chancen |
| Fernschüsse | Vermeiden · **Ausgewogen** · Fordern | Vermeiden: Geduld, auf bessere Gelegenheiten warten |
| Flankenstil | **Ausgewogen** · Hohe Flanken · Kraftvolle Flanken · Flache Flanken | Flach: "spielt den Ball in den Fuß". Hoch: Lufthoheit nutzen |
| Unterstützende Läufe | Hinterlaufen: **Ausgewogen** · Links · Rechts · Auf beiden Flügeln. Vorderlaufen: **Ausgewogen** · Links · Rechts · Auf beiden Flügeln | Zwei getrennte Einstellungen. Ausgewogen: "nicht mehr als normal" |
| Aufbauspiel | **Ausgewogen** · Links · Zentrum · Rechts · Beide Flügel | Fokus auf einen Bereich; Ausgewogen: situationsabhängig |
| Pass-Aufnahme | Pass in den Fuß · **Ausgewogen** · Pass in die Tiefe | Fuß: weniger Steilpässe. Tiefe: mehr Steilpässe, "Läufe in den Raum" |
| Spielaufbau-Strategie | Durch Pressing spielen · **Ausgewogen** · Pressing umgehen | Durch Pressing: mehr Risiko, unter Druck ruhig bleiben. Umgehen: weniger Risiko, unter Druck vertikale Bälle |
| Abstöße | Kurz · **Gemischt** · Lang | Gemischt: Anteil kurz/lang hängt von der Vertikalität des Passspiels ab |
| Spielaufbau TW (Geschwindigkeit) | Spiel verzögern · **Ausgewogen** · Spiel schnell fortsetzen | Schnell: Konter einleiten. Verzögern: warten, bis die Mannschaft in Position ist |
| Spielaufbau TW (Ziel) | Über gegnerische Verteidigung · Zielspieler · Flügel (l) · Spielmacher · Flügel (r) · Außenverteidiger (l) · Innenverteidiger · Außenverteidiger (r) · **Ausgewogen** | Ausgewogen: TW entscheidet selbst |

Fett = Ist-Stand Werder, 03.07.2027.

## Was es nicht gibt
- **Keine eigene Anweisung für Seitenwechsel/Spielverlagerung.** Nächste Hebel: Angriffsbreite (Breiter), Aufbauspiel (Beide Flügel), Passspiel. Ob das zu mehr Seitenwechseln führt, ist nicht getestet.
- Keine Anweisung "Flanken seltener"; Flankenstil ist die Art, nicht die Häufigkeit (Geduld steuert früh/spät).
- Gegenläufige Bewegungen: am ehesten über Unterstützende Läufe (Hinterlaufen/Vorderlaufen) und Pass-Aufnahme (Pass in die Tiefe), sonst über Rollen. Wirkung nicht getestet.

# Ohne Ball

| Anweisung | Stufen | Wirkung laut UI (Plus / Minus) |
|---|---|---|
| Pressinglinie | Tiefer Block · **Mittlerer Block** · Hohes Pressing | Tief: Gegner im vorderen Drittel anlaufen. Mittel: im Frühstadium des Angriffs anlaufen, verdichtet das Mittelfeld, lässt den Verteidigern Zeit, "hohe Ballgewinne unwahrscheinlicher". Hoch: während des Spielaufbaus anlaufen |
| Defensivlinie | Viel tiefer · Tiefer · Standard · **Höher** · Viel höher | Höher: weniger Raum zwischen den Linien, mehr Abseits; Minus: "deutlich anfälliger für direkte Steilpässe", "deutlich stärker vom Keeper abhängig, dass er Pässe abfängt" |
| Verhalten Defensivlinie | Mehr Aufrücken · **Ausgewogen** · Weiter zurückziehen | Aufrücken: Linie so hoch wie möglich. Zurückziehen: achtsam bei Bällen in die Tiefe |
| Pressingauslösung | Viel seltener · Seltener · **Standard** · Häufiger · Viel häufiger | Seltener: Formation halten, passiver. Häufiger: häufiger anlaufen, aktiver. Standard: Formation schlechter gehalten als seltener, Gegner mehr Zeit als intensiver |
| Defensives Umschalten | Neu formieren · **Standard** · Gegenpressing | Neu formieren: sofort Formation einnehmen, Ballführenden ausbremsen. Standard: situativ Gegenpressing oder Formation. Gegenpressing: sofort stören, Ball schnell zurückgewinnen |
| Tackling | Im Duell auf den Beinen bleiben · **Standard** · Mehr in die Zweikämpfe gehen | Beine: Position halten, stellen. Mehr: Gegenspieler in Manndeckung, in die Zweikämpfe |
| Pressingfalle | Pressingfallen im Zentrum · **Ausgewogen** · Pressingfallen auf Außen | Zentrum: Außen dicht, Ball im Zentrum erobern. Außen: Zentrum dicht, Ball außen erobern |
| Torwart – Spielaufbau (gegnerischer TW) | **Nein** · Ja | Nein: auf Pressinglinie zurückziehen, weniger anfällig für vertikale Bälle. Ja: Aufbau stören, zu langen Pässen zwingen |
| Gegnerische Flanken (Name im Panel nicht sichtbar) | Flanken verhindern · **Ausgewogen** · Flanken zulassen | Verhindern: Außenspieler attackieren. Zulassen: Zentrum absichern |
