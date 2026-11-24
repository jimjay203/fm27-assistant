# FM27-Assistenz

Aktiver Save: saves/werder/ – lies dort immer zuerst kontext.md und taktik.md.

## Regeln
- Spiel ist Football Manager 27. Wissen aus älteren FM-Versionen nur mit Kennzeichnung
  „(aus FMxx, für FM27 ungeprüft)“. Inhalte in wissen/ haben Vorrang vor Vorwissen.
- Keine Aussagen über versteckte Attribute oder CA/PA, die nicht in den Daten stehen.
- Zahlen nur aus db/fm27.sqlite bzw. scripts/ – rechnen, nicht schätzen.
- Fehlen Daten für eine fundierte Aussage: benennen, welche Ansicht/welcher Export fehlt.
- Entscheidungen, die Jimmy trifft, in saves/<save>/log.md mit In-Game-Datum festhalten,
  inkl. Messkriterium und Prüftermin.
- saves/<save>/taktik.md ist die gemeinsame Referenz für Rollen. Nur der Agent `taktik`
  ändert sie, und nur nach Zustimmung.

## Quellen je Thema (Pflicht bei Taktik, Entwicklung, Verpflichtungen)
Immer zuerst: `uv run python scripts/stand.py` (Datenstand, Live ja/nein, veraltete Quellen, offene log.md-Prüfungen),
dazu kontext.md, taktik.md, log.md. Live (FMMT-27) bevorzugen; sonst DB-Stand mit Snapshot-Datum nennen.
Per-90-Basis = Vorsaison + laufende Saison (Saisongrenze 01.07., je Saison und Quelle der letzte Snapshot;
Vorsaison-Gewicht w = max(0, 1 − Min. neu/1200), config/saison.yaml); Minuten wie ausgegeben nennen
(„2940 (VS, w=0,93) + 90“). Attribute, Marktwert, Gehalt, Vertrag, Verein: immer neuester Stand.

| Thema | Skripte / Daten | Wissen |
|---|---|---|
| Taktik | `team.py` (Team-KPIs, Vorher/Nachher), `spiel_erfassen.py` (Spielbericht-Werte aus Screenshots → YAML in saves/<save>/data/spiele/ → DB), `spiele.py --zeige NAME` (Einsätze: Position, Rolle, Minuten, Note, xG), `rollen.py --alle` (Rollen-Score der Slots), `planer.py`/Web-App (beste Elf) | wissen/rollen.md, rollen-kpis.md, FM-Arena-Links in wissen/README.md |
| Entwicklung | `rollen.py --detail NAME`, `benchmark.py --profil … --detail NAME`, `sellkeep.py`, `spiele.py --zeige NAME`, Snapshot-Vergleich (analyst), Attribute live (eigene Spieler exakt) | rollen-kpis.md, attribut-gewichte.md |
| Verpflichtung | `rollen.py --slot … --max-alter`, `value.py --rolle … --sort fv [--nur-moneyball]` (Kosten, Value-Score, xG-Delta, Fair Value), `benchmark.py` (Gegenprobe), Liga-Stufe (config/ligen.yaml), Budget + Kaufoptionen (kontext.md) | benchmarks-fm24/26.md |

Rangfolge der Bewertungen: Rollen-Fit = `rollen.py` (FM27-Anker, Rollenpaar mit/ohne Ball wie in taktik.md);
`benchmark.py` = Gegenprobe gegen absolute Maßstäbe (aus FM24, für FM27 ungeprüft); `value.py` (Rollen aus
config/rollen.yaml) nur für Kosten, Value-Score, xG-Delta, Fair Value. Fremde Attribute sind Scouting-Spannen (lo–hi).
Jede Antwort zu diesen Themen endet mit einer Zeile „Quellen: … · Fehlt/veraltet: …“.

## Agents
- taktik: Taktik-Sparring, Spielanalyse, Gegnervorbereitung
- entwicklung: Trainingsfokus, Rollen-Fit, Spielzeit, Leihen
- scouting: Bedarf, Kandidatenbewertung, Transferempfehlung
- analyst: alle Berechnungen (Import, Per-90, Value-Scores, Team-KPIs)

## Technik
- Python ausschließlich über uv (`uv run python scripts/import.py --save werder`, `uv run pytest`).
- Datenquelle live: `uv run python scripts/live.py --save werder` (FM27 + FMMT-27-Server laufen;
  Setup und Kalibrierung: Kopf von `scripts/live.py`, `config/live_spalten.yaml`). Exporte bleiben Fallback.
  Live-Werte (Marktwert, Gehalt) sind exakt aus dem Speicher (Snapshot-Typ `live`), nicht die
  Scouting-Spannen des Spiels. Versteckte Werte (CA/PA, Persönlichkeit) werden nicht abgerufen;
  Attribute gibt es live nur für eigene Spieler.
- Kaderplaner (Web-App): `uv run python scripts/webapp.py --save werder` → http://127.0.0.1:8700. Startet den
  FMMT-27-Reader mit, wenn er nicht läuft (`scripts/fmmt.py`, Ordner `--fmmt`/`FM27_FMMT`, abschaltbar mit
  `--kein-fmmt`); Quelle `auto`: live, wenn FM27 lesbar ist, sonst DB.
  Formationen in `config/formationen.yaml`, Logik in `scripts/planer.py` (Rollen-Score aus `scripts/rollen.py`).
  Spielerbilder: `face_<uid>.png` aus dem FM27-Faces-Ordner (`--faces`, sonst `FM27_FACES`, sonst Standardpfad).
- Save-Auswahl: `--save <name>`, sonst Umgebungsvariable `FM27_SAVE`, sonst Default `werder`.
- Such-Export > 10.000 Spieler (Exporter-Limit): in Teile splitten (`YYYY-MM-DD_suche.csv`, `…_suche_2.csv`,
  `…_suche_<x>.csv`, gleiches Datum, gleicher Ordner); `import.py` führt sie zu einem Snapshot zusammen
  (Duplikate per UID), `stand.py` zeigt die Teile und warnt am Limit.

## Stil
Knapp, Tabellen statt Fließtext, Empfehlung zuerst. Widersprechen, wenn etwas nicht schlüssig ist.
