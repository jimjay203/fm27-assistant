"""Gegen den Ball über mehrere Spiele: Form ohne Ball, Reihenabstände, Anspiele zwischen den Linien,
Herkunft der Gegenschüsse und Gegentore, Ballgewinne und Gegnerprofil mit Ball.

Grundlage sind alle importierten SpielLogger-Mitschnitte (Tabelle spiel_logs). Positionen, Ereignisse und Spieler
stammen aus dem Spiel. Reihen, Abstände, Seiten, Auslöser, Aufbaureihe und Gegnertyp sind EIGENE ABLEITUNGEN.
xG gegen stammt aus dem Spielbericht (team_matches). Seiten werden immer aus UNSERER Sicht angegeben
(„links“ = unsere linke Abwehrseite, LV).

Aufruf:  uv run python scripts/gegenball.py [--seit 2027-11-01] [--gegner Stuttgart] [--reihen 4-2-3-1]
         [--ohne-grafik]
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import namen
import spielanalyse as sa
import spieldaten
import spielimport
import spielkennzahlen as kz
from spieldaten import Spiel

STRAFRAUM_HALB = 20.15
SPANNE_REIHE = 8.0  # m: Spieler innerhalb dieser Tiefe gehören zur tiefsten bzw. höchsten Reihe


# ---------------------------------------------------------------------- Bausteine (reine Funktionen)


def parse_reihen(text: str) -> tuple[int, ...]:
    teile = tuple(int(t) for t in text.split("-"))
    if sum(teile) != 10 or any(t <= 0 for t in teile):
        raise ValueError(f"Reihen '{text}' ergeben keine 10 Feldspieler")
    return teile


def feldspieler(spiel: Spiel, team: int, positionen: dict, n: int = 10) -> dict:
    """Die n Feldspieler mit der meisten Messzeit (ohne Torwart): {uid: (quer, längs, stichproben)}."""
    tw = {s.uid for s in spiel.spieler.values() if s.index in spiel.torwart(team)}
    kandidaten = {u: w for u, w in positionen.items() if u not in tw}
    return dict(sorted(kandidaten.items(), key=lambda kv: -kv[1][2])[:n])


def reihen(positionen: dict, aufteilung: tuple[int, ...]) -> list[dict]:
    """Feldspieler nach Tiefe (eigenes Tor zuerst) in Reihen teilen -> je Reihe Tiefe, Breite, Spieler (links→rechts)."""
    sortiert = sorted(positionen.items(), key=lambda kv: kv[1][1])
    ergebnis, start = [], 0
    for anzahl in aufteilung:
        teil = sortiert[start : start + anzahl]
        start += anzahl
        if not teil:
            break
        quer = [w[0] for _, w in teil]
        ergebnis.append({
            "laengs": statistics.fmean(w[1] for _, w in teil),
            "breite": max(quer) - min(quer),
            "spieler": [u for u, _ in sorted(teil, key=lambda kv: kv[1][0])],
            "orte": [(w[0], w[1]) for _, w in sorted(teil, key=lambda kv: kv[1][0])],
        })  # fmt: skip
    return ergebnis


def linienzahl(tiefen: list[float], tiefste: bool = True, spanne: float = SPANNE_REIHE) -> int:
    """Wie viele Spieler stehen innerhalb `spanne` m der tiefsten (bzw. höchsten) Position?"""
    if not tiefen:
        return 0
    rand = min(tiefen) if tiefste else max(tiefen)
    return sum(abs(t - rand) <= spanne for t in tiefen)


def bahn(quer: float) -> str:
    """Seite aus unserer Sicht (wir greifen nach oben an, quer > 0 = rechts)."""
    kanal = abs(quer)
    seite = "rechts" if quer > 0 else "links"
    return (
        "Mitte"
        if kanal < 7
        else f"Halbraum {seite}"
        if kanal < STRAFRAUM_HALB
        else f"Flügel {seite}"
    )


def seite_grob(quer: float) -> str:
    return "Mitte" if abs(quer) < 7 else "rechts" if quer > 0 else "links"


def ausloeser_art(text: str) -> str:
    t = text.lower()
    if t.startswith("konter"):
        return "Konter"
    if any(s in t for s in ("ecke", "freistoß", "einwurf", "abstoß", "anstoß")):
        return "Standard"
    if t == "unklar":
        return "unklar"
    return "Ballbesitz"


def gegnertyp(aufbau: int) -> str:
    return "Aufbau 2er" if aufbau <= 2 else "Aufbau 3er" if aufbau == 3 else "Aufbau 4er+"


# ---------------------------------------------------------------------- Auswertung je Spiel


@dataclass
class Spielwerte:
    datum: str
    gegner: str
    form: dict  # ohne Ball: linie, laenge, breite, sekunden
    reihen: list[dict]
    zwischen: int = 0
    gegner_paesse: int = 0
    gegenschuesse: list[dict] = field(default_factory=list)
    gegentore: list[dict] = field(default_factory=list)
    gewinne: Counter = field(default_factory=Counter)
    verluste_gegenschuss: int = 0
    verluste: int = 0
    aufbau: int = 0
    spitze: int = 0
    gegner_seiten: Counter = field(default_factory=Counter)
    xg_gegen: float | None = None
    fluegel: dict = field(default_factory=dict)

    @property
    def typ(self) -> str:
        return gegnertyp(self.aufbau)

    def abstand(self, i: int) -> float | None:
        return (
            self.reihen[i + 1]["laengs"] - self.reihen[i]["laengs"]
            if len(self.reihen) > i + 1
            else None
        )


def herkunft(spiel: Spiel, wir: int, t: sa.Tor, info: dict | None = None) -> dict:
    """Gegnerangriff aus unserer Sicht: Seite beim Eintritt in unser Drittel, Ort des Ballgewinns, Auslöser."""
    eintritt, start = None, None
    for e in t.kette:
        ball = spiel.ball_bei(e.ts)
        if not ball:
            continue
        quer, laengs = spiel.lage(wir, e.ts, ball)
        if start is None:
            start = laengs
        if laengs < -17.5:
            eintritt = (quer, laengs)
            break
    if eintritt is None:
        ball = spiel.ball_bei(t.abschluss.ts)
        eintritt = spiel.lage(wir, t.abschluss.ts, ball) if ball else None
    ort = spiel.ball_bei(t.abschluss.ts)
    schuss = spiel.lage(wir, t.abschluss.ts, ort) if ort else None
    return {
        "minute": spiel.minute(t.ts),
        "schuetze": spiel.name(t.schuetze) if t.schuetze else "–",
        "seite": bahn(eintritt[0]) if eintritt else "unklar",
        "seite_grob": seite_grob(eintritt[0]) if eintritt else "unklar",
        "start": "unklar" if start is None else "unser Drittel" if start < -17.5 else "Mitte" if start <= 17.5 else "ihr Drittel",
        "art": ausloeser_art(t.ausloeser),
        "ausloeser": t.ausloeser,
        "ort": schuss,
        "chance": (info or {}).get("chance", ""),
        "tor_m": (info or {}).get("tor_m"),
    }  # fmt: skip


def zwischen_den_linien(spiel: Spiel, wir: int, aufteilung: tuple[int, ...]) -> tuple[int, int]:
    """Angekommene Gegnerpässe, deren Empfänger zentral zwischen unserer Kette und der nächsten Reihe steht."""
    gegner = 1 - wir
    tw = {s.uid for s in spiel.spieler.values() if s.index in spiel.torwart(wir)}
    n_kette, n_mitte = aufteilung[0], aufteilung[1]
    treffer = gesamt = 0
    for e, danach in kz.ballaktionen(spiel):
        if e.kat not in ("pass", "flanke") or spiel.team(e.uids[0]) != gegner:
            continue
        if not danach or spiel.team(danach.uids[0]) != gegner:
            continue
        gesamt += 1
        pos = spiel.positionen(danach.ts)
        empfaenger = pos.get(danach.uids[0])
        unsere = sorted(
            spiel.lage(wir, danach.ts, p)[1]
            for u, p in pos.items()
            if spiel.team(u) == wir and u not in tw
        )
        if not empfaenger or len(unsere) < n_kette + n_mitte:
            continue
        kette = statistics.fmean(unsere[:n_kette])
        mitte = statistics.fmean(unsere[n_kette : n_kette + n_mitte])
        quer, laengs = spiel.lage(wir, danach.ts, empfaenger)
        if kette < laengs < mitte and abs(quer) < STRAFRAUM_HALB:
            treffer += 1
    return treffer, gesamt


def auswerten(
    spiel: Spiel, wir: int, datum: str, gegner_name: str, aufteilung: tuple[int, ...]
) -> Spielwerte:
    gegner = 1 - wir
    form = kz.mannschaftsform(spiel, wir).get(False, {})
    ohne = feldspieler(spiel, wir, kz.mittlere_positionen(spiel, wir).get(False, {}))
    w = Spielwerte(datum, gegner_name, form, reihen(ohne, aufteilung))
    w.zwischen, w.gegner_paesse = zwischen_den_linien(spiel, wir, aufteilung)
    for t, info in kz.szenen(spiel):
        if t.team == gegner:
            w.gegenschuesse.append(herkunft(spiel, wir, t, info))
    w.gegentore = [herkunft(spiel, wir, t) for t in sa.tore(spiel) if t.team == gegner]
    gewinne, verluste = kz.wechsel_des_ballbesitzes(spiel, wir)
    w.gewinne = Counter(kz.drittel(o[1]) for _, o in gewinne)
    schuesse = spielimport.schuesse(spiel)
    w.verluste = len(verluste)
    w.verluste_gegenschuss = sum(kz.schuss_binnen(spiel, e, gegner, schuesse) for e, _ in verluste)
    mit = feldspieler(spiel, gegner, kz.mittlere_positionen(spiel, gegner).get(True, {}))
    tiefen = [v[1] for v in mit.values()]
    w.aufbau, w.spitze = linienzahl(tiefen), linienzahl(tiefen, tiefste=False)
    # Gegnerseiten spiegeln: ihr links = unser rechts
    spiegel = {"links": "rechts", "rechts": "links", "Mitte": "Mitte"}
    w.gegner_seiten = Counter(
        {spiegel[k]: v for k, v in kz.abspiele_nach_seite(spiel, gegner).items()}
    )
    w.fluegel = fluegelmomente(spiel, wir, w.reihen)
    return w


def fluegelmomente(
    spiel: Spiel, wir: int, reihen_: list[dict], aussen: float = 15.0, nah: float = 10.0
) -> dict:
    """Gegner hat den Ball in unserer Hälfte außen (|quer| >= `aussen`): wie nah sind wir dran?

    Flügelspieler = äußerster Spieler der Seite außerhalb der Kette, AV = äußerster Kettenspieler (aus `reihen_`).
    -> {seite: {sekunden, om_hinter (Anteil Flügel zwischen Ball und eigenem Tor), om_vor_ball (m, Median),
    om_abstand, av_abstand (m, Median), nah (Ø eigene Feldspieler im Umkreis `nah` m)}}"""
    if len(reihen_) < 2:
        return {}
    kette = reihen_[0]
    vorne = [(u, o) for r in reihen_[1:] for u, o in zip(r["spieler"], r["orte"], strict=True)]
    rollen = {
        "links": (min(vorne, key=lambda x: x[1][0])[0], kette["spieler"][0]),
        "rechts": (max(vorne, key=lambda x: x[1][0])[0], kette["spieler"][-1]),
    }
    tw = {s.uid for s in spiel.spieler.values() if s.index in spiel.torwart(wir)}
    werte: dict = {"links": [], "rechts": []}
    for ts, besitz, pos in kz.raster(spiel):
        if besitz == wir:
            continue
        ball = spiel.ball_bei(ts)
        if not ball:
            continue
        bq, bl = spiel.lage(wir, ts, ball)
        if bl > 0 or abs(bq) < aussen:
            continue
        seite = "rechts" if bq > 0 else "links"
        om, av = rollen[seite]
        if om not in pos or av not in pos:
            continue
        lage = {
            u: spiel.lage(wir, ts, q)
            for u, q in pos.items()
            if spiel.team(u) == wir and u not in tw
        }
        abstand = {u: math.dist(o, (bq, bl)) for u, o in lage.items()}
        werte[seite].append((lage[om][1] < bl, lage[om][1] - bl, abstand[om], abstand[av],
                             sum(d < nah for d in abstand.values())))  # fmt: skip
    return {
        seite: {
            "sekunden": len(v),
            "om_hinter": sum(x[0] for x in v) / len(v),
            "om_vor_ball": statistics.median(x[1] for x in v),
            "om_abstand": statistics.median(x[2] for x in v),
            "av_abstand": statistics.median(x[3] for x in v),
            "nah": statistics.fmean(x[4] for x in v),
        }
        for seite, v in werte.items() if v
    }  # fmt: skip


# ---------------------------------------------------------------------- Ausgabe


def _m(v: float | None) -> str:
    return "–" if v is None else f"{v:.0f}"


def _anteil(teil: int, ganz: int) -> str:
    return f"{teil} ({100 * teil / ganz:.0f} %)" if ganz else "–"


def _spanne(werte: list[float], fmt: str = "{:.0f}") -> str:
    werte = [v for v in werte if v is not None]
    if not werte:
        return "–"
    mittel = fmt.format(statistics.fmean(werte))
    return (
        mittel
        if len(werte) == 1
        else f"{mittel} ({fmt.format(min(werte))}–{fmt.format(max(werte))})"
    )


def bericht(alle: list[Spielwerte], aufteilung: tuple[int, ...]) -> str:
    t = kz._tabelle
    namen_reihen = {0: "Kette–2. Reihe", 1: "2.–3. Reihe", 2: "3.–4. Reihe"}
    z = [
        f"# Gegen den Ball · {len(alle)} Spiele · Reihen ohne Ball {'-'.join(map(str, aufteilung))} (eigene Ableitung)"
    ]

    z.append("\n## Form ohne Ball je Spiel (Median bzw. mittlere Positionen, Meter)")
    kopf = ["Datum", "Gegner", "Kette vor Tor", "Länge", "Breite"]
    kopf += [namen_reihen[i] for i in range(len(aufteilung) - 1)]
    kopf += ["Breite Kette", "Breite 2. Reihe", "zwischen den Linien", "xG gegen (Bericht)"]
    zeilen = []
    for w in alle:
        zeile = [
            w.datum,
            w.gegner,
            _m(w.form.get("linie")),
            _m(w.form.get("laenge")),
            _m(w.form.get("breite")),
        ]
        zeile += [_m(w.abstand(i)) for i in range(len(aufteilung) - 1)]
        zeile += [_m(w.reihen[0]["breite"]) if w.reihen else "–", _m(w.reihen[1]["breite"]) if len(w.reihen) > 1 else "–",
                  _anteil(w.zwischen, w.gegner_paesse), "–" if w.xg_gegen is None else f"{w.xg_gegen:.2f}"]  # fmt: skip
        zeilen.append(zeile)
    z.append(t(kopf, zeilen))
    z.append(
        "„zwischen den Linien“: angekommene Gegnerpässe, Empfänger zentral (Strafraumbreite) zwischen Kette und 2. Reihe."
    )

    z.append("\n## Gegnerprofil mit Ball (eigene Ableitung)")
    zeilen = []
    for w in alle:
        ges = sum(w.gegner_seiten.values())
        seiten = (
            ", ".join(
                f"{s} {100 * w.gegner_seiten[s] / ges:.0f} %" for s in ("links", "Mitte", "rechts")
            )
            if ges
            else "–"
        )
        konter = sum(s["art"] == "Konter" for s in w.gegenschuesse)
        zeilen.append(
            [
                w.datum,
                w.gegner,
                w.aufbau,
                w.spitze,
                w.typ,
                seiten,
                _anteil(konter, len(w.gegenschuesse)),
            ]
        )
    z.append(
        t(
            [
                "Datum",
                "Gegner",
                "Aufbaureihe",
                "Spitze",
                "Typ",
                "Abspiele vorn (unsere Seite)",
                "Konter-Schüsse",
            ],
            zeilen,
        )
    )
    z.append(
        f"Aufbaureihe/Spitze: Gegner-Feldspieler mit Ball innerhalb {SPANNE_REIHE:.0f} m der tiefsten/höchsten mittleren Position."
    )

    z.append("\n## Gegenschüsse nach Seite (Eintritt in unser Drittel) und Auslöser")
    matrix: dict = defaultdict(Counter)
    for w in alle:
        for s in w.gegenschuesse:
            matrix[s["seite"]][s["art"]] += 1
    arten = ["Ballbesitz", "Konter", "Standard", "unklar"]
    reihenfolge = [
        "Flügel links",
        "Halbraum links",
        "Mitte",
        "Halbraum rechts",
        "Flügel rechts",
        "unklar",
    ]
    zeilen = [
        [s, *(matrix[s][a] for a in arten), sum(matrix[s].values())]
        for s in reihenfolge
        if matrix[s]
    ]
    zeilen.append(
        [
            "Summe",
            *(sum(matrix[s][a] for s in matrix) for a in arten),
            sum(sum(c.values()) for c in matrix.values()),
        ]
    )
    z.append(t(["Seite (unsere Sicht)", *arten, "gesamt"], zeilen))
    gross = [s for w in alle for s in w.gegenschuesse if s["chance"] == "Großchance"]
    if gross:
        z.append(
            "Großchancen gegen: "
            + ", ".join(f"{k} {n}" for k, n in Counter(s["seite"] for s in gross).most_common())
        )

    z.append("\n## Gegentore (eigene Zuordnung; bei Abweichung gilt der Spielbericht)")
    zeilen = [[w.datum, w.gegner, g["minute"], g["schuetze"], g["seite"], g["start"], g["art"], g["ausloeser"]]
              for w in alle for g in w.gegentore]  # fmt: skip
    z.append(
        t(
            [
                "Datum",
                "Gegner",
                "Min",
                "Schütze",
                "Seite (unsere Sicht)",
                "Ballgewinn in",
                "Art",
                "Auslöser",
            ],
            zeilen,
        )
        if zeilen
        else "keine"
    )

    z.append(
        "\n## Flügelmomente: Gegner hat den Ball in unserer Hälfte außen (≥ 15 m neben der Mitte)"
    )
    zeilen = []
    for w in alle:
        for seite in ("links", "rechts"):
            f = w.fluegel.get(seite)
            if f:
                zeilen.append([w.datum, w.gegner, seite, f["sekunden"], f"{100 * f['om_hinter']:.0f} %",
                               _m(f["om_vor_ball"]), _m(f["om_abstand"]), _m(f["av_abstand"]), f"{f['nah']:.1f}"])  # fmt: skip
    for seite in ("links", "rechts"):
        fs = [w.fluegel[seite] for w in alle if seite in w.fluegel]
        if fs:
            sek = sum(f["sekunden"] for f in fs)
            zeilen.append(["Summe/Ø", "", seite, sek,
                           f"{100 * sum(f['om_hinter'] * f['sekunden'] for f in fs) / sek:.0f} %",
                           _m(statistics.median(f["om_vor_ball"] for f in fs)),
                           _m(statistics.median(f["om_abstand"] for f in fs)),
                           _m(statistics.median(f["av_abstand"] for f in fs)),
                           f"{sum(f['nah'] * f['sekunden'] for f in fs) / sek:.1f}"])  # fmt: skip
    z.append(t(["Datum", "Gegner", "Seite", "Sekunden", "Flügel hinter Ball", "Flügel vor Ball m",
                "Abstand Flügel m", "Abstand AV m", "eigene ≤10 m"], zeilen) if zeilen else "keine")  # fmt: skip
    z.append(
        "Flügel = äußerster Spieler der Seite vor der Kette; Summe/Ø: Anteile zeitgewichtet, Meter Median der Spiele."
    )

    z.append("\n## Zugriff")
    zeilen = [[w.datum, w.gegner, w.gewinne["eigenes Drittel"], w.gewinne["Mitte"], w.gewinne["vorderes Drittel"],
               _anteil(w.verluste_gegenschuss, w.verluste)] for w in alle]  # fmt: skip
    z.append(
        t(
            [
                "Datum",
                "Gegner",
                "Gewinne eig. Drittel",
                "Mitte",
                "vorn",
                "Verluste mit Gegenschuss ≤15 s",
            ],
            zeilen,
        )
    )

    z.append("\n## Nach Gegnertyp (Mittel, in Klammern Spanne; kleine Zahlen, kein Beleg)")
    gruppen: dict = defaultdict(list)
    for w in alle:
        gruppen[w.typ].append(w)
    zeilen = []
    for typ, ws in sorted(gruppen.items()):
        zeilen.append([
            typ, len(ws), ", ".join(w.gegner for w in ws),
            _spanne([len(w.gegenschuesse) for w in ws]),
            _spanne([w.xg_gegen for w in ws], "{:.2f}"),
            _spanne([100 * w.zwischen / w.gegner_paesse for w in ws if w.gegner_paesse]),
            _spanne([w.abstand(0) for w in ws]),
            _spanne([w.form.get("linie") for w in ws]),
        ])  # fmt: skip
    z.append(t(["Typ", "Spiele", "Gegner", "Gegenschüsse", "xG gegen", "zwischen den Linien %", "Kette–2. Reihe m",
                "Kette vor Tor m"], zeilen))  # fmt: skip
    return "\n".join(z)


def grafik(alle: list[Spielwerte], pfad: Path) -> Path:
    """Links: mittlere Reihenform ohne Ball je Gegnertyp. Rechts: Orte der Gegenschüsse (unser Tor unten)."""
    plt = kz._plt()
    fig, (links, rechts) = plt.subplots(1, 2, figsize=(13, 10.5))
    farben = {"Aufbau 2er": "#ffd54f", "Aufbau 3er": "#ef5350", "Aufbau 4er+": "#4fc3f7"}
    sa._feld(links)
    gruppen: dict = defaultdict(list)
    for w in alle:
        gruppen[w.typ].append(w)
    for typ, ws in gruppen.items():
        punkte: dict = defaultdict(list)
        for w in ws:
            for r, reihe in enumerate(w.reihen):
                for k, ort in enumerate(reihe["orte"]):
                    punkte[r, k].append(ort)
        for orte in punkte.values():
            x = statistics.fmean(o[0] for o in orte)
            y = statistics.fmean(o[1] for o in orte)
            links.scatter(
                x,
                y,
                s=140,
                c=farben.get(typ, "white"),
                edgecolors="white",
                linewidths=1.4,
                zorder=3,
            )
        links.scatter([], [], c=farben.get(typ, "white"), label=f"{typ} ({len(ws)})")
    links.legend(loc="upper right", fontsize=8)
    links.set_title("mittlere Form ohne Ball je Gegnertyp", fontsize=10)
    sa._feld(rechts)
    stil = {
        "Ballbesitz": "#ffffff",
        "Konter": "#ef5350",
        "Standard": "#ffd54f",
        "unklar": "#9e9e9e",
    }
    for art, farbe in stil.items():
        orte = [s["ort"] for w in alle for s in w.gegenschuesse if s["art"] == art and s["ort"]]
        if orte:
            rechts.scatter([o[0] for o in orte], [o[1] for o in orte], s=40, c=farbe, edgecolors="black",
                           linewidths=0.5, zorder=3, label=f"{art} ({len(orte)})")  # fmt: skip
    tore = [g["ort"] for w in alle for g in w.gegentore if g["ort"]]
    if tore:
        rechts.scatter([o[0] for o in tore], [o[1] for o in tore], s=160, marker="*", c="#ff1744",
                       edgecolors="white", zorder=4, label=f"Gegentor ({len(tore)})")  # fmt: skip
    rechts.legend(loc="upper right", fontsize=8)
    rechts.set_title("Gegenschüsse nach Auslöser (unser Tor unten)", fontsize=10)
    fig.suptitle(
        f"Gegen den Ball · {len(alle)} Spiele · Angriffsrichtung Werder nach oben · eigene Ableitung",
        fontsize=11,
    )
    return kz._speichern(plt, fig, pfad)


# ---------------------------------------------------------------------- Ablauf


def spiele_laden(
    conn, save: str, seit: str | None, gegner: str | None, ordner: Path, config_dir=None
):
    """-> [(datum, gegner, Spiel)] aus spiel_logs; fehlende Dateien werden gemeldet und übersprungen."""
    zeilen = conn.execute(
        "SELECT datum, gegner, quelle FROM spiel_logs WHERE save=? ORDER BY datum", (save,)
    ).fetchall()
    ergebnis, fehlend = [], []
    for datum, name, quelle in zeilen:
        if seit and datum < seit:
            continue
        if gegner and namen.name_norm(gegner) not in namen.name_norm(name):
            continue
        pfad = ordner / quelle
        if not pfad.exists():
            fehlend.append(f"{datum} {name}: {quelle}")
            continue
        ergebnis.append((datum, name, spieldaten.laden(pfad, True, config_dir)))
    return ergebnis, fehlend


def xg_gegen(conn, save: str, datum: str) -> float | None:
    r = conn.execute(
        "SELECT xg_against FROM team_matches WHERE save=? AND ingame_date=? AND xg_against IS NOT NULL",
        (save, datum),
    ).fetchone()
    return r[0] if r else None


def main(argv=None) -> None:
    common.setup_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    common.add_common_args(ap)
    ap.add_argument("--seit", help="nur Spiele ab diesem In-Game-Datum (YYYY-MM-DD)")
    ap.add_argument("--gegner", help="nur Spiele gegen diesen Gegner (Teilname)")
    ap.add_argument(
        "--reihen",
        default="4-2-3-1",
        help="Reihen ohne Ball von hinten nach vorn (Default 4-2-3-1)",
    )
    ap.add_argument("--ordner", type=Path, default=spieldaten.LOG_ORDNER, help="Logger-Ordner")
    ap.add_argument("--ohne-grafik", action="store_true")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    try:
        aufteilung = parse_reihen(a.reihen)
    except ValueError as fehler:
        common.die(str(fehler))
        raise SystemExit(1) from fehler
    conn = common.connect(a.db)
    conn.executescript(spielimport.SCHEMA)
    spiele, fehlend = spiele_laden(conn, save, a.seit, a.gegner, a.ordner, a.config_dir)
    for f in fehlend:
        print(f"Mitschnitt fehlt, übersprungen: {f}")
    if not spiele:
        common.die("Keine importierten Mitschnitte gefunden (spielimport.py).")
        raise SystemExit(1)
    alle = []
    for datum, name, spiel in spiele:
        wir = spieldaten.unser_team(spiel, conn, save)
        w = auswerten(spiel, wir, datum, name, aufteilung)
        w.xg_gegen = xg_gegen(conn, save, datum)
        alle.append(w)
    print(bericht(alle, aufteilung))
    if not a.ohne_grafik:
        pfad = (
            common.save_dir(save)
            / "data"
            / "analyse"
            / "gegenball"
            / f"gegenball_{alle[0].datum}_{alle[-1].datum}.png"
        )
        print(f"\nGrafik: {grafik(alle, pfad)}")


if __name__ == "__main__":
    main()
