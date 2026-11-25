"""Spielanalyse aus dem SpielLogger-Mitschnitt: Torbeschreibungen mit Spielfeld-Grafik.

Ereignisse, Spieler und Positionen stammen aus dem Spiel; Auslöser, Konter, Abstände, Linienhöhe und Tempo sind
EIGENE ABLEITUNGEN. Gezeigt wird nur, was bereits gespielt/gesehen wurde (--alles hebt das auf).

Aufruf:  uv run python scripts/spielanalyse.py tore|szenen [--nr 2]
         uv run python scripts/spielanalyse.py spieler Grüll [--halb 1]
         uv run python scripts/spielanalyse.py team [--gegner] [--halb 1]
         uv run python scripts/spielanalyse.py halbzeit
         Optionen: --datei x.jsonl[.gz] · --ohne-grafik · --alles
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import spieldaten
from spieldaten import JE_SEKUNDE, Ereignis, Spiel

TORLINIE, HALBE_BREITE = 52.5, 34.0
KONTROLLE = {"pass", "flanke", "dribbling", "torwart", "schuss"}  # Gegner damit = unser Angriff beginnt danach
STUMM = {"kommentar", "pfiff", "zuruf", "wechsel"}
STANDARDS = {
    "TakeShortCorner": "kurze Ecke", "TakeCorner": "Ecke", "TakeThrowIn": "Einwurf", "TakeFreeKick": "Freistoß",
    "TakeGoalKick": "Abstoß", "KickOff": "Anstoß", "StartMatch": "Anstoß",
}  # fmt: skip


@dataclass
class Tor:
    ts: int
    team: int
    schuetze: int | None
    vorlage: int | None
    abschluss: Ereignis
    kette: list[Ereignis]
    ausloeser: str
    hinweise: list[str] = field(default_factory=list)


def aktion(spiel: Spiel, e: Ereignis) -> str:
    """Deutsche Beschreibung eines Ereignisses (ohne Spielernamen)."""
    n = e.name
    zweiter = e.uids[1] if len(e.uids) > 1 else None
    eigen = zweiter is not None and spiel.team(zweiter) == spiel.team(e.uids[0])
    an = f" → {spiel.name(zweiter)}" if eigen else ""
    gegen = f" gegen {spiel.name(zweiter)}" if zweiter is not None and not eigen else ""
    direkt = " direkt" if "FirstTime" in n else ""
    if e.kat == "pass":
        art = next((t for s, t in (
            ("OneTwo", "Doppelpass"), ("Head", "Kopfballpass"), ("Long", "langer Ball"), ("Short", "Kurzpass"),
            ("Medium", "mittellanger Pass"), ("AttemptPass", "Flachpass"),
        ) if s in n), "Pass")  # fmt: skip
        ziel = " in den Lauf" if "IntoPath" in n else " in den Strafraum" if "IntoArea" in n else ""
        ziel += " in den freien Raum" if "NoDestination" in n else ""
        weite = f" (~{e.laenge} m)" if e.laenge > 0 else ""
        return f"{art}{direkt}{ziel}{weite}{an}{gegen}"
    if e.kat == "flanke":
        art = " flach" if "Low" in n else " hoch" if "High" in n else ""
        pfosten = " an den langen Pfosten" if "FarPost" in n else " an den kurzen Pfosten" if "NearPost" in n else ""
        return f"Flanke{art}{direkt}{pfosten}{an}"
    if e.kat == "dribbling":
        tempo = " mit Tempo" if "Pace" in n else ""
        return f"geht{tempo} an {spiel.name(zweiter)} vorbei" if gegen else f"Dribbling{tempo}"
    if e.kat == "standard":
        return next((t for s, t in STANDARDS.items() if n.startswith(s)), n)
    if e.kat == "schuss":
        return "Kopfball aufs Tor" if "Header" in n else "Schuss"
    if e.kat == "torwart":
        return "Abwurf" if "Throw" in n else "nimmt den Ball auf" if "PickUp" in n else "Abschlag"
    fest = {
        "lauf": "läuft dem Ball nach", "abfangen": "fängt ab", "zweikampf": "gewinnt den Zweikampf", "klaerung": "klärt/köpft weg",
        "luftduell": "Duell um den Ball", "parade": "Parade",
        "block": "blockt", "foul": "Foul", "tor": "TOR", "abseits": "Abseits", "elfmeter": "Elfmeterpfiff",
    }  # fmt: skip
    return fest.get(e.kat, n) + gegen


def zone(quer: float, laengs: float) -> str:
    """Zone aus Sicht des angreifenden Teams (nach oben, rechts = rechte Angriffsseite)."""
    if laengs > TORLINIE - 16.5 and abs(quer) < 20.15:
        return "Strafraum " + ("zentral" if abs(quer) < 9.16 else "rechts" if quer > 0 else "links")
    drittel = "eigenes Drittel" if laengs < -17.5 else "Mitteldrittel" if laengs <= 17.5 else "Angriffsdrittel"
    kanal = abs(quer)
    seite = "rechts" if quer > 0 else "links"
    bahn = "Mitte" if kanal < 7 else f"Halbraum {seite}" if kanal < 20 else f"Flügel {seite}"
    return f"{drittel}, {bahn}"


def _schritte(kette: list[Ereignis]) -> list[Ereignis]:
    """Ohne Kommentarzeilen und Doppelmeldungen (gleiche Zeit, gleicher Spieler, gleiche Kategorie)."""
    gesehen, ergebnis = set(), []
    for e in kette:
        schluessel = (e.ts // 2, tuple(e.uids[:1]), e.kat)
        if e.kat in STUMM or schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        ergebnis.append(e)
    return ergebnis


def tore(spiel: Spiel) -> list[Tor]:
    ev = spiel.ereignisse
    ergebnis, letzte = [], -100
    for k, t in enumerate(ev):
        if t.kat != "tor" or t.ts - letzte < 20:
            continue
        letzte = t.ts
        team = _torteam(spiel, t)
        kandidaten = [
            (j, e) for j, e in enumerate(ev[: k + 1])
            if e.kat == "schuss" and e.uids and t.ts - 40 <= e.ts <= t.ts and spiel.team(e.uids[0]) == team
        ]  # fmt: skip
        hinweise = []
        if kandidaten:
            letzter = kandidaten[-1][1]
            j, abschluss = next(
                (j, e) for j, e in kandidaten if e.uids[0] == letzter.uids[0] and letzter.ts - e.ts <= 12
            )
            schuetze = abschluss.uids[0]
        else:
            j, abschluss = k, t
            schuetze = t.uids[0] if t.uids else None
            hinweise.append("Kein Schuss-Ereignis vor dem Tor (Eigentor oder unbekannter Ereignisname)")
        if t.uids and schuetze is not None and t.uids[0] != schuetze:
            hinweise.append(f"Tor-Ereignis nennt {spiel.name(t.uids[0])} (möglicherweise abgefälscht)")
        vorlage = next(
            (u for u in t.uids[1:2] if u != schuetze and spiel.team(u) == team), None
        )
        kette, vor_kette = angriff(spiel, j, team)
        ergebnis.append(Tor(
            t.ts, team, schuetze, vorlage, abschluss, kette,
            ausloeser(spiel, team, kette, vor_kette, abschluss), hinweise,
        ))  # fmt: skip
    return ergebnis


def angriff(spiel: Spiel, j: int, team: int) -> tuple[list[Ereignis], Ereignis | None]:
    """Angriff von `team` bis zum Ereignis j: zurück bis zum eigenen Standard oder bis der Gegner den Ball
    kontrolliert hat. -> (Schritte, letzte gegnerische Ballaktion davor)."""
    ev = spiel.ereignisse
    start = j
    while start > 0:
        davor = ev[start - 1]
        eigen = spiel.team_von(davor) == team
        if davor.kat == "standard" and eigen:
            start -= 1
            break
        if (davor.kat in KONTROLLE | {"standard"} and davor.uids and not eigen) or davor.kat == "tor":
            break
        if ev[start].ts - davor.ts > 60 * JE_SEKUNDE:
            break
        start -= 1
    vor = next((e for e in reversed(ev[:start]) if e.kat in KONTROLLE | {"standard"} and e.uids), None)
    return _schritte(ev[start:j + 1]), vor


def _torteam(spiel: Spiel, t: Ereignis) -> int:
    """Wer angreift, dessen Zieltor liegt auf der Seite, auf der der Ball beim Tor ist."""
    ball = spiel.ball_bei(t.ts, 8)
    if ball and abs(ball[2]) > 40:
        for team in (0, 1):
            if spiel.richtung(team, t.ts) * ball[2] > 0:
                return team
    return spiel.team_von(t) or 0


def ausloeser(spiel: Spiel, team: int, kette, vor_kette, abschluss) -> str:
    if not kette:
        return "unklar"
    erster = kette[0]
    dauer = (abschluss.ts - erster.ts) / JE_SEKUNDE
    a, b = spiel.ball_bei(erster.ts), spiel.ball_bei(abschluss.ts)
    raum = spiel.lage(team, abschluss.ts, b)[1] - spiel.lage(team, erster.ts, a)[1] if a and b else None
    if erster.kat == "standard":
        text = aktion(spiel, erster)
        return f"{text} (direkt)" if dauer <= 12 else f"nach {text}, {dauer:.0f} s eigener Ballbesitz"
    eigener = next((e for e in kette if e.uids and spiel.team(e.uids[0]) == team), None)
    wer = f" durch {spiel.name(eigener.uids[0])}" if eigener else ""
    verlust = ""
    if vor_kette and spiel.team(vor_kette.uids[0]) != team:
        verlust = f" nach {aktion(spiel, vor_kette)} von {spiel.name(vor_kette.uids[0])}"
    # Konter: vom Spiel gemeldet oder viel Raum in kurzer Zeit (mind. 35 m in höchstens 20 s, im Schnitt 3 m/s)
    schnell = raum is not None and raum >= 35 and dauer <= 20 and raum / max(dauer, 1) >= 3
    konter = any(e.kat == "konter" for e in kette) or schnell
    return f"{'Konter, ' if konter else ''}Ballgewinn{wer}{verlust}"


# ---------------------------------------------------------------------- Momentaufnahmen


def _abstand(a, b) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def moment(spiel: Spiel, team: int, ts: int, spieler: int | None) -> dict | None:
    """Lage um `spieler` (Angreifer) zum Zeitpunkt ts: Gegnerabstand, Gegner hinter dem Ball, Linie, Torwart."""
    pos = spiel.positionen(ts)
    ball = spiel.ball_bei(ts)
    if not pos or spieler not in pos or ball is None:
        return None
    gegner_tw = {s.uid for s in spiel.spieler.values() if s.index in spiel.torwart(1 - team)}
    gegner = {u: p for u, p in pos.items() if spiel.team(u) != team and u not in gegner_tw}
    if not gegner:
        return None
    ich = pos[spieler]
    naechster = min(gegner, key=lambda u: _abstand(ich, gegner[u]))
    tiefen = sorted((spiel.lage(team, ts, p)[1] for p in gegner.values()), reverse=True)
    linie = sum(tiefen[:4]) / len(tiefen[:4])
    quer, laengs = spiel.lage(team, ts, ich)
    tw = next((pos[u] for u in gegner_tw if u in pos), None)
    return {
        "zone": zone(quer, laengs),
        "tor_m": math.hypot(quer, TORLINIE - laengs),
        "gegner": naechster,
        "gegner_m": _abstand(ich, gegner[naechster]),
        "hinter_ball": sum(t > spiel.lage(team, ts, ball)[1] for t in tiefen),
        "linie_m": TORLINIE - linie,  # Abstand der vier tiefsten Verteidiger zu ihrem Tor
        "vor_linie_m": laengs - linie,  # > 0: Angreifer hinter der Kette
        "tw_linie_m": TORLINIE - spiel.lage(team, ts, tw)[1] if tw else None,
        "tw_m": _abstand(ich, tw) if tw else None,
    }


def spitzentempo(spiel: Spiel, uid: int, von: int, bis: int) -> float | None:
    """km/h über Fenster von 1 s; None ohne dichte Messungen."""
    werte = []
    for ts in range(von, bis - JE_SEKUNDE + 1):
        a, b = spiel.positionen(ts, 2).get(uid), spiel.positionen(ts + JE_SEKUNDE, 2).get(uid)
        if a and b:
            werte.append(_abstand(a, b) * 3.6)
    plausibel = [w for w in werte if w <= 40]
    return max(plausibel) if plausibel else None


def ueberschrift(spiel: Spiel, t: Tor, nr: int, wir: int) -> str:
    s, v = t.schuetze, t.vorlage
    wer = "WIR" if t.team == wir else "GEGENTOR"
    stand = [sum(x.team == team for x in tore(spiel) if x.ts <= t.ts) for team in (0, 1)]
    return (
        f"Tor {nr} · {spiel.minute(t.ts)} ({spiel.uhr(t.ts)}) · {stand[0]}:{stand[1]} · {wer}: "
        f"{spiel.name(s) if s else '?'}" + (f" (Vorlage {spiel.name(v)})" if v else "")
    )


def beschreibung(spiel: Spiel, t: Tor, nr: int, wir: int, titel: str | None = None) -> str:
    s, v = t.schuetze, t.vorlage
    z = [f"## {titel or ueberschrift(spiel, t, nr, wir)}", f"Auslöser: {t.ausloeser}"]
    if t.kette:
        erster, a = t.kette[0], spiel.ball_bei(t.kette[0].ts)
        b = spiel.ball_bei(t.abschluss.ts)
        dauer = (t.abschluss.ts - erster.ts) / JE_SEKUNDE
        paesse = sum(e.kat in ("pass", "flanke") and spiel.team_von(e) == t.team for e in t.kette)
        raum = ""
        if a and b:
            raum = f" · {spiel.lage(t.team, t.abschluss.ts, b)[1] - spiel.lage(t.team, erster.ts, a)[1]:.0f} m Raumgewinn"
        z.append(f"Angriff: {dauer:.0f} s · {paesse} Pässe/Flanken{raum}")
    z += ["", "| Zeit | Spieler | Aktion | Ort (Sicht des Angreifers) |", "|---|---|---|---|"]
    for e in t.kette:
        name = spiel.name(e.uids[0]) if e.uids else "–"
        if e.uids and spiel.team(e.uids[0]) != t.team:
            name += " (Gegner)" if t.team == wir else " (wir)"
        p = spiel.ball_bei(e.ts)
        ort = zone(*spiel.lage(t.team, e.ts, p)) if p else "–"
        z.append(f"| {spiel.uhr(e.ts)} | {name} | {aktion(spiel, e)} | {ort} |")
    vorlage_ev = next((e for e in reversed(t.kette) if v and e.uids[:1] == [v]), None)
    if vorlage_ev:
        m = moment(spiel, t.team, vorlage_ev.ts, s)
        if m:
            z.append(
                f"\nBei der Vorlage: {spiel.name(s)} in {m['zone']}, nächster Gegner {spiel.name(m['gegner'])} "
                f"{m['gegner_m']:.1f} m · Abwehrkette {m['linie_m']:.0f} m vor dem Tor, Schütze "
                f"{abs(m['vor_linie_m']):.1f} m {'hinter' if m['vor_linie_m'] > 0 else 'vor'} ihr"
            )
    m = moment(spiel, t.team, t.abschluss.ts, s) if s else None
    if m:
        tw = "" if m["tw_m"] is None else f" · Torwart {m['tw_linie_m']:.1f} m vor der Linie, {m['tw_m']:.1f} m entfernt"
        z.append(
            f"Beim Abschluss: {m['tor_m']:.0f} m zum Tor ({m['zone']}) · nächster Gegner {spiel.name(m['gegner'])} "
            f"{m['gegner_m']:.1f} m · {m['hinter_ball']} Feldspieler hinter dem Ball{tw}"
        )
        start = vorlage_ev.ts if vorlage_ev else t.abschluss.ts - 5 * JE_SEKUNDE
        von = min(start, t.abschluss.ts - 5 * JE_SEKUNDE)
        v1 = spitzentempo(spiel, s, von, t.abschluss.ts)
        v2 = spitzentempo(spiel, m["gegner"], von, t.abschluss.ts)
        if v1 is not None and v2 is not None:
            z.append(f"Spitzentempo davor: {spiel.name(s)} {v1:.0f} km/h, {spiel.name(m['gegner'])} {v2:.0f} km/h")
    else:
        z.append("\nBeim Abschluss: keine Positionsmessung")
    z += [f"Hinweis: {h}" for h in t.hinweise]
    return "\n".join(z)


# ---------------------------------------------------------------------- Grafik


def _feld(ax) -> None:
    from matplotlib.patches import Circle, Rectangle

    ax.set_facecolor("#2f6b3c")
    stil = {"fill": False, "edgecolor": "white", "linewidth": 1}
    ax.add_patch(Rectangle((-HALBE_BREITE, -TORLINIE), 2 * HALBE_BREITE, 2 * TORLINIE, **stil))
    ax.plot([-HALBE_BREITE, HALBE_BREITE], [0, 0], color="white", linewidth=1)
    ax.add_patch(Circle((0, 0), 9.15, **stil))
    for s in (1, -1):
        for breite, tiefe in ((40.32, 16.5), (18.32, 5.5), (7.32, -2)):
            ax.add_patch(Rectangle((-breite / 2, s * TORLINIE), breite, -s * tiefe, **stil))
    ax.set_xlim(-HALBE_BREITE - 2, HALBE_BREITE + 2)
    ax.set_ylim(-TORLINIE - 3, TORLINIE + 3)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def momente(spiel: Spiel, t: Tor) -> list[tuple[int, str]]:
    """Ausgangslage, Aufbau, Vorlage (bzw. 3 s vorher) und Abschluss, zeitlich geordnet.

    Aufbau = der weiteste Pass dazwischen, sonst die Mitte. Sehr kurze Angriffe: Blick vor den Angriffsbeginn."""
    vorlage = next((e for e in reversed(t.kette) if t.vorlage and e.uids[:1] == [t.vorlage]), None)
    dritter = vorlage.ts if vorlage else t.abschluss.ts - 3 * JE_SEKUNDE
    beginn = t.kette[0].ts if t.kette else t.abschluss.ts
    erster = max(0, min(beginn, dritter - 4 * JE_SEKUNDE))
    dazwischen = [
        e for e in t.kette
        if e.kat in ("pass", "flanke") and erster + JE_SEKUNDE < e.ts < dritter - JE_SEKUNDE
    ]  # fmt: skip
    zweiter = max(dazwischen, key=lambda e: e.laenge).ts if dazwischen else (erster + dritter) // 2
    return [
        (erster, "Ausgangslage" if erster == beginn else "kurz vor Angriffsbeginn"),
        (zweiter, "Aufbau"),
        (dritter, "Vorlage" if vorlage else "3 s vor dem Abschluss"),
        (t.abschluss.ts, "Abschluss"),
    ]


def grafik(spiel: Spiel, t: Tor, titel: str, pfad: Path, wir: int, zeitpunkte: list[tuple[int, str]]) -> None:
    """Je Zeitpunkt ein Feld mit allen Spielern und dem Ballweg bis dahin."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    start = zeitpunkte[0][0] if zeitpunkte else t.abschluss.ts
    start = min(start, t.kette[0].ts if t.kette else start)
    fig, achsen = plt.subplots(1, len(zeitpunkte), figsize=(6.5 * len(zeitpunkte), 10.5))
    for ax, (ts, name) in zip(achsen, zeitpunkte, strict=True):
        _feld(ax)
        weg = [spiel.lage(t.team, x, spiel.ball[x]) for x in sorted(spiel.ball) if start <= x <= ts]
        if weg:
            ax.plot(*zip(*weg, strict=True), color="#ffd54f", linewidth=1.5, alpha=0.9, zorder=2)
        for n, e in enumerate(t.kette, 1):
            p = spiel.ball_bei(e.ts)
            if p and e.ts <= ts:
                x, y = spiel.lage(t.team, e.ts, p)
                ax.text(x, y, str(n), fontsize=7, ha="center", va="center", zorder=5,
                        bbox={"boxstyle": "circle,pad=0.15", "fc": "#ffd54f", "ec": "none"})  # fmt: skip
        pos = spiel.positionen(ts)
        for uid, p in pos.items():
            x, y = spiel.lage(t.team, ts, p)
            farbe = "#009655" if spiel.team(uid) == wir else "#d9d9d9"
            rand = "black" if uid in (t.schuetze, t.vorlage) else "white"
            ax.scatter(x, y, s=110, c=farbe, edgecolors=rand, linewidths=1.6, zorder=3)
            ax.text(x, y - 2.4, spiel.name(uid), fontsize=7, color="white", ha="center", zorder=4)
        b = spiel.ball_bei(ts)
        if b:
            x, y = spiel.lage(t.team, ts, b)
            ax.scatter(x, y, s=40, c="white", edgecolors="black", zorder=6)
        ohne = "" if pos else " · keine Positionsmessung"
        ax.set_title(f"{name} ({spiel.uhr(ts)}){ohne}", fontsize=10)
    fig.suptitle(f"{titel}\ngrün = wir · grau = Gegner · Angriffsrichtung nach oben · gelb = Ballweg", fontsize=11)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(pfad, dpi=110)
    plt.close(fig)


def grafiken(spiel: Spiel, t: Tor, titel: str, basis: Path, wir: int) -> list[Path]:
    """<basis>_1.png: Ausgangslage + Aufbau, <basis>_2.png: Vorlage + Abschluss."""
    vier = momente(spiel, t)
    ziele = []
    for n, paar in enumerate((vier[:2], vier[2:]), 1):
        ziel = basis.with_name(f"{basis.name}_{n}.png")
        grafik(spiel, t, titel, ziel, wir, paar)
        ziele.append(ziel)
    return ziele


# ---------------------------------------------------------------------- Aufruf


def kontext(conn, save: str, spiel: Spiel) -> tuple[int, str]:
    """(unser Team, Ordnername <datum>_<gegner>)."""
    import spielimport

    wir = spieldaten.unser_team(spiel, conn, save)
    datum, gegner = spielimport.zuordnung(conn, save, spiel, wir)
    return wir, spielimport.slug(datum, gegner) if datum else spiel.datei.name.split(".")[0]


def main(argv=None) -> None:
    import spielkennzahlen as kz

    common.setup_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("befehl", choices=["tore", "szenen", "spieler", "team", "halbzeit"])
    ap.add_argument("name", nargs="?", help="spieler: Name")
    common.add_common_args(ap)
    ap.add_argument("--datei", type=Path, help="Mitschnitt (Default: neuestes Spiel im Logger-Ordner)")
    ap.add_argument("--nr", type=int, help="tore/szenen: nur diese Nummer ausführlich")
    ap.add_argument("--halb", type=int, choices=[1, 2], help="spieler/team: nur diese Halbzeit")
    ap.add_argument("--gegner", action="store_true", help="team: den Gegner auswerten")
    ap.add_argument("--alles", action="store_true", help="auch noch nicht gespielte Ereignisse")
    ap.add_argument("--ohne-grafik", action="store_true")
    a = ap.parse_args(argv)
    save = common.resolve_save(a.save)
    spiel = spieldaten.laden(a.datei or spieldaten.neuester(), a.alles, a.config_dir)
    conn = common.connect(a.db)
    wir, ordner = kontext(conn, save, spiel)
    ziel = None if a.ohne_grafik else common.save_dir(save) / "data" / "analyse" / ordner
    print(f"Mitschnitt {spiel.datei.name} · gesehen bis {spiel.uhr(spiel.gesehen)}")
    if a.befehl == "tore":
        liste = tore(spiel)
        if not liste:
            print("Noch kein Tor.")
        for nr, t in enumerate(liste, 1):
            if a.nr and nr != a.nr:
                continue
            print()
            print(beschreibung(spiel, t, nr, wir))
            if ziel:
                titel = f"Tor {nr}, {spiel.minute(t.ts)}: {spiel.name(t.schuetze)}"
                for pfad in grafiken(spiel, t, titel, ziel / f"tor_{nr}", wir):
                    print(f"Grafik: {pfad}")
    elif a.befehl == "szenen":
        print(kz.szenen_text(spiel, wir, a.nr, ziel))
    elif a.befehl == "spieler":
        if not a.name:
            common.die("Name fehlt: spielanalyse.py spieler Grüll")
            raise SystemExit(1)
        print(kz.spieler_text(spiel, wir, a.name, a.halb, ziel))
    elif a.befehl == "team":
        print(kz.team_text(spiel, 1 - wir if a.gegner else wir, wir, a.halb, ziel))
    else:
        print(kz.halbzeit_text(spiel, wir, ziel))

if __name__ == "__main__":
    main()
