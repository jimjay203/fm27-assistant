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

## Stil
Knapp, Tabellen statt Fließtext, Empfehlung zuerst. Widersprechen, wenn etwas nicht schlüssig ist.
