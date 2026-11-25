"""Szenen-, Spieler-, Team- und Halbzeitauswertung eines Mitschnitts (Aufruf über spielanalyse.py).

Alles hier sind EIGENE ABLEITUNGEN aus Ereignissen und Positionsmessungen:
- Pass angekommen = die nächste Ballaktion gehört demselben Team.
- Ballbesitz je Zeitpunkt = Team der letzten kontrollierten Ballaktion.
- Positionswerte: 1 Stichprobe je Spielsekunde, nur wo gemessen wurde (tote Zeit fehlt).
"""

from __future__ import annotations

import itertools
import math
import statistics
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import namen
import spielanalyse as sa
import spielimport
from spieldaten import JE_SEKUNDE, Ereignis, Spiel

BALL = {"pass", "flanke", "dribbling", "torwart", "schuss", "standard", "abfangen", "zweikampf", "klaerung",
        "luftduell", "lauf", "parade", "block"}  # fmt: skip
BESITZ = {"pass", "flanke", "dribbling", "torwart", "schuss", "standard"}
GEWINN = {"abfangen", "zweikampf"}
HALBZEIT = {1: "FirstHalf", 2: "SecondHalf"}


def _in_halbzeit(spiel: Spiel, ts: int, halb: int | None) -> bool:
    return halb is None or spiel.zeit(ts)[0] == HALBZEIT[halb]


def _ort(spiel: Spiel, team: int, ts: int) -> tuple[float, float] | None:
    p = spiel.ball_bei(ts)
    return spiel.lage(team, ts, p) if p else None


def _tabelle(kopf: list[str], zeilen: list[list]) -> str:
    if not zeilen:
        return "–"
    return "\n".join(
        ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
        + ["| " + " | ".join(str(z) for z in zeile) + " |" for zeile in zeilen]
    )


def ballaktionen(spiel: Spiel) -> list[tuple[Ereignis, Ereignis | None]]:
    """(Aktion, nächste Ballaktion) für alle Ereignisse mit Spieler am Ball."""
    liste = [e for e in spiel.ereignisse if e.uids and e.kat in BALL]
    return list(zip(liste, liste[1:] + [None], strict=False))


def paesse(spiel: Spiel, team: int, halb: int | None = None) -> list[tuple[Ereignis, int | None]]:
    """(Pass/Flanke des Teams, uid des Mitspielers, bei dem er ankam | None)."""
    ergebnis = []
    for e, danach in ballaktionen(spiel):
        if e.kat not in ("pass", "flanke") or spiel.team(e.uids[0]) != team or not _in_halbzeit(spiel, e.ts, halb):
            continue
        an = danach.uids[0] if danach and spiel.team(danach.uids[0]) == team else None
        ergebnis.append((e, an))
    return ergebnis


def wechsel_des_ballbesitzes(spiel: Spiel, team: int, halb: int | None = None):
    """-> (Ballgewinne, Ballverluste) als (Ereignis, (quer, längs) aus Sicht von `team`)."""
    gewinne, verluste = [], []
    besitz = None
    for e, _ in ballaktionen(spiel):
        t = spiel.team(e.uids[0])
        if e.kat not in BESITZ | GEWINN:
            continue
        if besitz is not None and t != besitz and e.kat != "standard" and _in_halbzeit(spiel, e.ts, halb):
            ort = _ort(spiel, team, e.ts)
            if ort:
                (gewinne if t == team else verluste).append((e, ort))
        besitz = t
    return gewinne, verluste


def drittel(laengs: float) -> str:
    return "eigenes Drittel" if laengs < -17.5 else "Mitte" if laengs <= 17.5 else "vorderes Drittel"


# ---------------------------------------------------------------------- Szenen


def szenen(spiel: Spiel) -> list[tuple[sa.Tor, dict]]:
    """Jeder Schuss mit seinem Angriff und Ausgang."""
    index = {id(e): j for j, e in enumerate(spiel.ereignisse)}
    ergebnis = []
    for e in spielimport.schuesse(spiel):
        j, team = index[id(e)], spiel.team(e.uids[0])
        # Ausgang: was bis zum nächsten Schuss eines anderen Spielers passiert (3 s)
        danach = list(itertools.takewhile(
            lambda x, e=e: x.ts - e.ts <= 12 and not (x.kat == "schuss" and x.uids and x.uids[0] != e.uids[0]),
            spiel.ereignisse[j:],
        ))  # fmt: skip
        namen_danach = " ".join(x.name for x in danach)
        ausgang = next((text for teil, text in (
            ("GoalScored", "TOR"), ("GoalkeeperTippedWide", "pariert"), ("GoalieCatch", "gehalten"),
            ("GoalkeeperHeld", "gehalten"), ("GoalkeeperPunch", "pariert"), ("BlockShot", "geblockt"),
            ("HitsPost", "Pfosten"), ("ShotWide", "vorbei"), ("Over", "drüber"),
        ) if teil in namen_danach), "offen")  # fmt: skip
        grosse = any(x.name == "SilentClearCutChance" for x in danach)
        halbe = any(x.name == "SilentHalfChance" for x in danach)
        kette, vor = sa.angriff(spiel, j, team)
        vorlage = next(
            (x.uids[0] for x in reversed(kette[:-1])
             if x.kat in ("pass", "flanke") and x.uids and spiel.team(x.uids[0]) == team and x.uids[0] != e.uids[0]
             and e.ts - x.ts <= 10 * JE_SEKUNDE),
            None,
        )  # fmt: skip
        ort = _ort(spiel, team, e.ts)
        szene = sa.Tor(e.ts, team, e.uids[0], vorlage, e, kette, sa.ausloeser(spiel, team, kette, vor, e))
        ergebnis.append((szene, {
            "ausgang": ausgang,
            "chance": "Großchance" if grosse else "Halbchance" if halbe else "",
            "tor_m": math.hypot(ort[0], sa.TORLINIE - ort[1]) if ort else None,
            "kopfball": any("Header" in x.name for x in danach if x.kat == "schuss"),
        }))  # fmt: skip
    return ergebnis


def szenen_text(spiel: Spiel, wir: int, nr: int | None, ziel: Path | None) -> str:
    alle = szenen(spiel)
    if nr:
        if not 1 <= nr <= len(alle):
            return f"Szene {nr} gibt es nicht (1–{len(alle)})."
        t, info = alle[nr - 1]
        titel = f"Szene {nr} · {spiel.minute(t.ts)} · {spiel.name(t.schuetze)}: {info['ausgang']}"
        text = sa.beschreibung(spiel, t, nr, wir, titel)
        if ziel:
            text += "".join(
                f"\nGrafik: {p}" for p in sa.grafiken(spiel, t, titel, ziel / f"szene_{nr}", wir)
            )
        return text
    zeilen = [
        [n, spiel.minute(t.ts), "wir" if t.team == wir else "Gegner", spiel.name(t.schuetze),
         "–" if i["tor_m"] is None else f"{i['tor_m']:.0f} m{' (Kopf)' if i['kopfball'] else ''}",
         i["ausgang"], i["chance"], spiel.name(t.vorlage) if t.vorlage else "–", t.ausloeser]
        for n, (t, i) in enumerate(alle, 1)
    ]  # fmt: skip
    return "## Abschlüsse (eigene Zählung)\n" + _tabelle(
        ["#", "Min", "Team", "Schütze", "Distanz", "Ausgang", "laut Spiel", "letzter Pass", "Auslöser"], zeilen
    )


# ---------------------------------------------------------------------- Positionen


@lru_cache(maxsize=4)
def _raster_cache(kennung: int):
    spiel = _SPIELE[kennung]
    besitz = [(e.ts, spiel.team(e.uids[0])) for e, _ in ballaktionen(spiel) if e.kat in BESITZ | GEWINN]
    ergebnis, k, team = [], 0, None
    for ts in range(0, spiel.gesehen + 1, JE_SEKUNDE):
        while k < len(besitz) and besitz[k][0] <= ts:
            team = besitz[k][1]
            k += 1
        pos = spiel.positionen(ts)
        if pos and team is not None:
            ergebnis.append((ts, team, pos))
    return ergebnis


_SPIELE: dict[int, Spiel] = {}


def raster(spiel: Spiel, halb: int | None = None):
    """Je Spielsekunde mit Messung: (ts, Team im Ballbesitz, Positionen)."""
    _SPIELE[id(spiel)] = spiel
    return [r for r in _raster_cache(id(spiel)) if _in_halbzeit(spiel, r[0], halb)]


def mittlere_positionen(spiel: Spiel, team: int, halb: int | None = None, mindest: int = 300):
    """{mit Ball: bool -> {uid: (quer, längs, Stichproben)}} aus Sicht des Teams."""
    summen: dict = {True: defaultdict(list), False: defaultdict(list)}
    for ts, besitz, pos in raster(spiel, halb):
        for uid, p in pos.items():
            if spiel.team(uid) == team:
                summen[besitz == team][uid].append(spiel.lage(team, ts, p))
    return {
        mit: {
            uid: (statistics.fmean(x for x, _ in w), statistics.fmean(y for _, y in w), len(w))
            for uid, w in je.items() if len(w) >= mindest
        }
        for mit, je in summen.items()
    }  # fmt: skip


def mannschaftsform(spiel: Spiel, team: int, halb: int | None = None) -> dict:
    """Mit/ohne Ball: Linienhöhe (4 tiefste, Abstand zum eigenen Tor), Länge, Breite der Feldspieler (Median)."""
    torwart = {s.uid for s in spiel.spieler.values() if s.index in spiel.torwart(team)}
    werte: dict = {True: [], False: []}
    for ts, besitz, pos in raster(spiel, halb):
        feld = [spiel.lage(team, ts, p) for u, p in pos.items() if spiel.team(u) == team and u not in torwart]
        if len(feld) < 8:
            continue
        laengs = sorted(y for _, y in feld)
        quer = [x for x, _ in feld]
        werte[besitz == team].append(
            (sum(laengs[:4]) / 4 + sa.TORLINIE, laengs[-1] - laengs[0], max(quer) - min(quer))
        )
    return {
        mit: {
            "linie": statistics.median(w[0] for w in liste),
            "laenge": statistics.median(w[1] for w in liste),
            "breite": statistics.median(w[2] for w in liste),
            "sekunden": len(liste),
        }
        for mit, liste in werte.items() if liste
    }  # fmt: skip


# ---------------------------------------------------------------------- Grafiken


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    return plt


def _speichern(plt, fig, pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(pfad, dpi=110)
    plt.close(fig)
    return pfad


def team_grafik(spiel: Spiel, team: int, halb: int | None, titel: str, pfad: Path) -> Path:
    """Mittlere Positionen mit Ball (inkl. häufigster Passwege) und ohne Ball."""
    plt = _plt()
    pos = mittlere_positionen(spiel, team, halb)
    # Nur die elf mit der meisten Messzeit: Ein- und Ausgewechselte würden sich sonst überdecken
    dauer: Counter = Counter()
    for mit in pos.values():
        dauer.update({u: w[2] for u, w in mit.items()})
    elf = {u for u, _ in dauer.most_common(11)}
    pos = {k: {u: w for u, w in mit.items() if u in elf} for k, mit in pos.items()}
    netz = Counter((e.uids[0], an) for e, an in paesse(spiel, team, halb) if an and an != e.uids[0])
    fig, achsen = plt.subplots(1, 2, figsize=(13, 10.5))
    for ax, mit in zip(achsen, (True, False), strict=True):
        sa._feld(ax)
        if mit:
            for (a, b), n in netz.items():
                if n >= 5 and a in pos[mit] and b in pos[mit]:
                    ax.plot([pos[mit][a][0], pos[mit][b][0]], [pos[mit][a][1], pos[mit][b][1]],
                            color="#ffd54f", linewidth=min(n / 3, 7), alpha=0.6, zorder=2)  # fmt: skip
        for uid, (x, y, _) in pos[mit].items():
            ax.scatter(x, y, s=130, c="#009655", edgecolors="white", linewidths=1.6, zorder=3)
            ax.text(x, y - 2.6, spiel.name(uid), fontsize=8, color="white", ha="center", zorder=4)
        ax.set_title("mit Ball (gelb: Passweg ab 5 Pässen)" if mit else "ohne Ball", fontsize=10)
    fig.suptitle(f"{titel}\nmittlere Positionen der 11 mit der meisten Messzeit · Angriffsrichtung nach oben", fontsize=11)
    return _speichern(plt, fig, pfad)


def spieler_grafik(spiel: Spiel, uid: int, halb: int | None, titel: str, pfad: Path) -> Path:
    """Links Pässe (Start -> Ankunft), rechts Aufenthaltsorte mit/ohne Ball."""
    plt = _plt()
    team = spiel.team(uid)
    fig, achsen = plt.subplots(1, 2, figsize=(13, 10.5))
    for ax in achsen:
        sa._feld(ax)
    folge = {id(e): d for e, d in ballaktionen(spiel)}
    for e, an in paesse(spiel, team, halb):
        if e.uids[0] != uid:
            continue
        a = _ort(spiel, team, e.ts)
        d = folge.get(id(e))
        b = _ort(spiel, team, d.ts) if d else None
        if a and b:
            achsen[0].annotate("", xy=b, xytext=a, zorder=3, arrowprops={
                "arrowstyle": "->", "color": "#ffd54f" if an else "#ff5252", "linewidth": 1.2})  # fmt: skip
    punkte = defaultdict(list)
    for ts, besitz, pos in raster(spiel, halb):
        if uid in pos:
            punkte[besitz == team].append(spiel.lage(team, ts, pos[uid]))
    for mit, farbe in ((False, "#d9d9d9"), (True, "#ffd54f")):
        if punkte[mit]:
            achsen[1].scatter(*zip(*punkte[mit][::3], strict=True), s=8, c=farbe, alpha=0.5, zorder=3)
    achsen[0].set_title("Pässe: gelb angekommen, rot verloren", fontsize=10)
    achsen[1].set_title("Aufenthalt: gelb mit Ball, grau ohne", fontsize=10)
    fig.suptitle(f"{titel}\nAngriffsrichtung nach oben", fontsize=11)
    return _speichern(plt, fig, pfad)


# ---------------------------------------------------------------------- Spieler


def finde(spiel: Spiel, wir: int, name: str) -> int:
    n = namen.name_norm(name)
    treffer = [s for s in spiel.spieler.values() if s.art == "Player" and n in namen.name_norm(s.name)]
    treffer.sort(key=lambda s: s.team != wir)
    if not treffer:
        raise SystemExit(f"Spieler '{name}' nicht im Mitschnitt.")
    return treffer[0].uid


def tempo_spitze(spiel: Spiel, uid: int, halb: int | None) -> float | None:
    """99. Perzentil der 1-s-Geschwindigkeit (km/h), Ausreißer über 40 verworfen."""
    werte = []
    letzte: tuple[int, list] | None = None
    for ts, _, pos in raster(spiel, halb):
        if uid not in pos:
            letzte = None
            continue
        if letzte and ts - letzte[0] == JE_SEKUNDE:
            v = math.hypot(pos[uid][0] - letzte[1][0], pos[uid][2] - letzte[1][2]) * 3.6
            if v <= 40:
                werte.append(v)
        letzte = (ts, pos[uid])
    return sorted(werte)[int(len(werte) * 0.99)] if len(werte) >= 60 else None


def spieler_text(spiel: Spiel, wir: int, name: str, halb: int | None, ziel: Path | None) -> str:
    uid = finde(spiel, wir, name)
    team = spiel.team(uid)
    alle = paesse(spiel, team, halb)
    eigene = [(e, an) for e, an in alle if e.uids[0] == uid]
    an_ihn = Counter(e.uids[0] for e, an in alle if an == uid and e.uids[0] != uid)
    von_ihm = Counter(an for _, an in eigene if an and an != uid)

    def quote(liste):
        return f"{sum(a is not None for _, a in liste)}/{len(liste)}" + (
            f" ({100 * sum(a is not None for _, a in liste) / len(liste):.0f} %)" if liste else "")  # fmt: skip

    aktionen = Counter(
        e.kat for e, _ in ballaktionen(spiel) if e.uids[0] == uid and _in_halbzeit(spiel, e.ts, halb)
    )
    gewinne, _ = wechsel_des_ballbesitzes(spiel, team, halb)
    pos = mittlere_positionen(spiel, team, halb, mindest=60)
    z = [f"## {spiel.name(uid)}" + (f" · {halb}. Halbzeit" if halb else "")]
    zeilen = [
        ["Pässe angekommen", quote([p for p in eigene if p[0].kat == "pass"])],
        ["davon ab ~25 m", quote([p for p in eigene if p[0].kat == "pass" and p[0].laenge >= 25])],
        ["Flanken angekommen", quote([p for p in eigene if p[0].kat == "flanke"])],
        ["Schüsse", sum(e.uids[0] == uid and _in_halbzeit(spiel, e.ts, halb) for e in spielimport.schuesse(spiel))],
        ["Abgefangen / Zweikämpfe gewonnen", f"{aktionen['abfangen']} / {aktionen['zweikampf']}"],
        ["Dribblings", aktionen["dribbling"]],
        ["Klärungen / Blocks", f"{aktionen['klaerung']} / {aktionen['block']}"],
    ]  # fmt: skip
    fehl = Counter(drittel(o[1]) for e, an in eigene if an is None and (o := _ort(spiel, team, e.ts)))
    zeilen.append(["Fehlpässe je Zone (Abspielort)", ", ".join(f"{k} {n}" for k, n in fehl.most_common()) or "–"])
    zeilen.append(["Ballgewinne (Besitzwechsel)", sum(e.uids[0] == uid for e, _ in gewinne)])
    for mit, text in ((True, "mit Ball"), (False, "ohne Ball")):
        if uid in pos[mit]:
            x, y, n = pos[mit][uid]
            zeilen.append([f"Mittlere Position {text}",
                           (f"{y + sa.TORLINIE:.0f} m vor dem eigenen Tor, {abs(x):.0f} m "
                           f"{'rechts' if x > 0 else 'links'} ({n} s)")])  # fmt: skip
    v = tempo_spitze(spiel, uid, halb)
    zeilen.append(["Spitzentempo (99. Perzentil)", "–" if v is None else f"{v:.1f} km/h"])
    z.append(_tabelle(["Wert", "Ergebnis"], zeilen))
    z.append("\nSpielt am häufigsten zu: " + (", ".join(
        f"{spiel.name(u)} {n}" for u, n in von_ihm.most_common(4)) or "–"))  # fmt: skip
    z.append("Bekommt am häufigsten von: " + (", ".join(
        f"{spiel.name(u)} {n}" for u, n in an_ihn.most_common(4)) or "–"))  # fmt: skip
    if ziel:
        datei = ziel / f"spieler_{namen.name_norm(spiel.name(uid)).replace(' ', '-')}{halb or ''}.png"
        z.append(f"Grafik: {spieler_grafik(spiel, uid, halb, spiel.name(uid), datei)}")
    return "\n".join(z)


# ---------------------------------------------------------------------- Team


def team_text(spiel: Spiel, team: int, wir: int, halb: int | None, ziel: Path | None) -> str:
    wer = "Wir" if team == wir else "Gegner"
    z = [f"## {wer}" + (f" · {halb}. Halbzeit" if halb else "")]
    form = mannschaftsform(spiel, team, halb)
    z.append("\n### Form (Median, Feldspieler)")
    z.append(_tabelle(["Phase", "Abwehrkette vor eigenem Tor", "Länge", "Breite", "Stichprobe"], [
        ["mit Ball" if mit else "ohne Ball", f"{w['linie']:.0f} m", f"{w['laenge']:.0f} m", f"{w['breite']:.0f} m",
         f"{w['sekunden']} s"] for mit, w in sorted(form.items(), reverse=True)
    ]))  # fmt: skip
    gewinne, verluste = wechsel_des_ballbesitzes(spiel, team, halb)
    schuesse = spielimport.schuesse(spiel)

    def folgt_schuss(e: Ereignis, wessen: int) -> bool:
        return any(spiel.team(s.uids[0]) == wessen and 0 <= s.ts - e.ts <= 15 * JE_SEKUNDE for s in schuesse)

    z.append("\n### Ballbesitzwechsel")
    zeilen = []
    for d in ("eigenes Drittel", "Mitte", "vorderes Drittel"):
        g = [e for e, o in gewinne if drittel(o[1]) == d]
        v = [e for e, o in verluste if drittel(o[1]) == d]
        zeilen.append([d, len(g), sum(folgt_schuss(e, team) for e in g),
                       len(v), sum(folgt_schuss(e, 1 - team) for e in v)])  # fmt: skip
    z.append(_tabelle(["Zone", "Gewinne", "… eigener Schuss ≤15 s", "Verluste", "… Gegenschuss ≤15 s"], zeilen))
    alle = paesse(spiel, team, halb)
    angekommen = sum(an is not None for _, an in alle)
    if alle:
        z.append(f"\nPässe und Flanken angekommen: {angekommen}/{len(alle)} ({100 * angekommen / len(alle):.0f} %)")
    eintritte = Counter()
    for e, an in alle:
        o = _ort(spiel, team, e.ts)
        if o and o[1] > 17.5:
            seite = "Mitte" if abs(o[0]) < 11 else "rechts" if o[0] > 0 else "links"
            eintritte[seite] += 1
    gesamt = sum(eintritte.values())
    if gesamt:
        z.append("Abspiele im vorderen Drittel: " + ", ".join(
            f"{s} {eintritte[s]} ({100 * eintritte[s] / gesamt:.0f} %)" for s in ("links", "Mitte", "rechts")))
    netz = Counter((e.uids[0], an) for e, an in alle if an and an != e.uids[0])
    z.append("Häufigste Passwege: " + (", ".join(
        f"{spiel.name(a)}→{spiel.name(b)} {n}" for (a, b), n in netz.most_common(8)) or "–"))  # fmt: skip
    verlierer = Counter(e.uids[0] for e, an in alle if an is None)
    z.append("Meiste Fehlabspiele: " + (", ".join(
        f"{spiel.name(u)} {n}" for u, n in verlierer.most_common(5)) or "–"))  # fmt: skip
    if ziel:
        datei = ziel / f"team_{'wir' if team == wir else 'gegner'}{halb or ''}.png"
        z.append(f"Grafik: {team_grafik(spiel, team, halb, wer, datei)}")
    return "\n".join(z)


# ---------------------------------------------------------------------- Halbzeit


def halbzeit_text(spiel: Spiel, wir: int, ziel: Path | None) -> str:
    """Kompakter Stand bis jetzt; die Deutung (höchstens 3 Auffälligkeiten) macht der Co-Trainer."""
    stand = [sum(t.team == team for t in sa.tore(spiel)) for team in (0, 1)]
    z = [(f"# Stand {spiel.uhr(spiel.gesehen)}: {stand[0]}:{stand[1]} (Heim:Gast, wir = "
         f"{'Heim' if wir == 0 else 'Gast'})")]  # fmt: skip
    z.append(szenen_text(spiel, wir, None, None))
    for team in (wir, 1 - wir):
        z.append("\n" + team_text(spiel, team, wir, None, ziel))
    zeilen = []
    alle = paesse(spiel, wir)
    for uid in sorted({e.uids[0] for e, _ in alle}, key=spiel.name):
        eigene = [an for e, an in alle if e.uids[0] == uid]
        verlust = len(eigene) - sum(an is not None for an in eigene)
        zeilen.append([spiel.name(uid), len(eigene), f"{100 * (len(eigene) - verlust) / len(eigene):.0f} %", verlust])
    z.append("\n## Unsere Passspieler\n" + _tabelle(["Spieler", "Abspiele", "angekommen", "verloren"], zeilen))
    return "\n".join(z)
