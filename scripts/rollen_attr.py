"""Rollenbasierter Attribut-Filter: key-/preferred-Attribute je Rolle (config/rollen_attribute.yaml) gegen die
Liga-Schwelle des Zielvereins.

Je Spieler und Rollenpaar (mit/ohne Ball):
  key_mit / key_ohne  Ø der key-Attribute der Rolle (Mitte der Scouting-Spanne, eigene Spieler exakt)
  pref_mit            Ø der preferred-Attribute der Rolle mit Ball (ohne Ball hat die Quelle keine)
  key_fehlt / key_n   key-Attribute (beider Rollen, ohne Doppelte) mit Mitte < Schwelle / Anzahl bekannter
  key_unsicher        key-Attribute, die nicht SICHER über der Schwelle liegen (lo < Schwelle; enthält key_fehlt)
  ausfaelle           Liste der Ausfälle mit Wert bzw. Spanne
Ohne Eintrag in der Quelle (z. B. "Mittelstürmer|ohne") gibt es für diese Phase keinen Filter; das wird
ausgewiesen, nicht ersetzt. Der Filter verwirft nichts, er weist aus.

Schwelle: Liga-Stufe des Zielvereins (wir) -> liga_schwelle in rollen_attribute.yaml (Zuordnung bestätigt: Jimmy, 07.07.2027).
Attribute kommen aus der DB (player_attributes): bevorzugt der Snapshot der Spielerzeile, sonst der neueste
mit Attributen. Live liefert Attribute nur für eigene Spieler (siehe live.py).
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import common
import pandas as pd

PHASEN = ("mit", "ohne")


def laden(config_dir=None) -> dict:
    return common.load_yaml("rollen_attribute.yaml", config_dir)


def schwelle_fuer_stufe(stufe: str | None, ra: dict) -> int:
    """Mindestwert je Ansehen-Stufe (liga_schwelle), sonst liga_schwelle_default."""
    tab = ra.get("liga_schwelle") or {}
    if stufe in tab:
        return int(tab[stufe])
    return int(ra.get("liga_schwelle_default", 8))


def ziel_stufe(df: pd.DataFrame, lg) -> str | None:
    """Liga-Stufe des Zielvereins = häufigste Liga der eigenen Spieler."""
    if "own" not in df or "league" not in df:
        return None
    ligen = df.loc[df["own"].fillna(False).astype(bool), "league"].dropna()
    if ligen.empty:
        return None
    return lg.stufe(ligen.mode().iloc[0])


def rolle_def(name: str, phase: str, ra: dict, rk: dict | None = None) -> tuple[str, dict] | None:
    """(Schlüssel, Eintrag) der Rolle in rollen_attribute.yaml; Aliase aus rollen_kpis.yaml in beide Richtungen.

    Die Quelle (FM26) kann den FM27-Namen oder den Namen der Quelle führen (z. B. Spielaufbauender ↔
    Ballspielender Innenverteidiger). None, wenn die Quelle die Rolle in dieser Phase nicht hat."""
    rollen = ra.get("rollen") or {}
    alias = (rk or {}).get("alias_rollen") or {}
    namen = [name, alias.get(name)] + [k for k, v in alias.items() if v == name]
    for n in namen:
        if n and f"{n}|{phase}" in rollen:
            return f"{n}|{phase}", rollen[f"{n}|{phase}"]
    return None


def _mitte(v: tuple) -> tuple[float | None, float | None]:
    """(Wert, lo, hi) -> (Mitte, lo). Exakter Wert hat Vorrang; ohne Wert die Mitte der Spanne."""
    wert, lo, hi = v
    if _ok(wert):
        return float(wert), float(lo) if _ok(lo) else float(wert)
    if _ok(lo) and _ok(hi):
        return (float(lo) + float(hi)) / 2, float(lo)
    return None, None


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _fmt(v: tuple) -> str:
    wert, lo, hi = v
    if _ok(wert):
        return f"{wert:.0f}"
    if _ok(lo) and _ok(hi):
        return f"{lo:.0f}-{hi:.0f}"
    return "?"


def bewerten(attrs: dict[str, tuple], d: dict | None, schwelle: float) -> dict:
    """Eine Rolle: Ø key, Ø preferred, Ausfälle (Mitte < Schwelle), unsichere (lo < Schwelle), unbekannte."""
    if d is None:
        return {"vorhanden": False}
    out = {
        "vorhanden": True,
        "key": list(d.get("key") or []),
        "fehlt": [],
        "unsicher": [],
        "unbekannt": [],
    }
    werte = []
    for a in out["key"]:
        m, lo = _mitte(attrs.get(a, (None, None, None)))
        if m is None:
            out["unbekannt"].append(a)
            continue
        werte.append(m)
        if m < schwelle:
            out["fehlt"].append(a)
        if lo < schwelle:
            out["unsicher"].append(a)
    out["key_avg"] = sum(werte) / len(werte) if werte else None
    pref = [_mitte(attrs.get(a, (None, None, None)))[0] for a in d.get("preferred") or []]
    pref = [p for p in pref if p is not None]
    out["pref_avg"] = sum(pref) / len(pref) if pref else None
    return out


def paar(
    attrs: dict[str, tuple] | None, d_mit: dict | None, d_ohne: dict | None, schwelle: float
) -> dict:
    """Rollenpaar: Spaltenwerte für rollen.py. Doppelte key-Attribute (mit und ohne) zählen einmal."""
    leer = {"key_mit": None, "key_ohne": None, "pref_mit": None, "key_fehlt": None, "key_n": None,
            "key_unsicher": None, "ausfaelle": "keine Attribute in der DB"}  # fmt: skip
    if not attrs:
        return leer
    m, o = bewerten(attrs, d_mit, schwelle), bewerten(attrs, d_ohne, schwelle)
    keys = list(dict.fromkeys((m.get("key") or []) + (o.get("key") or [])))
    bekannt = [k for k in keys if _mitte(attrs.get(k, (None, None, None)))[0] is not None]
    fehlt = [k for k in keys if k in set(m.get("fehlt", [])) | set(o.get("fehlt", []))]
    unsicher = [k for k in keys if k in set(m.get("unsicher", [])) | set(o.get("unsicher", []))]
    teile = [f"{k} {_fmt(attrs[k])}" for k in fehlt]
    teile += [f"({k} {_fmt(attrs[k])} unsicher)" for k in unsicher if k not in fehlt]
    unbek = [k for k in keys if k not in bekannt]
    if unbek:
        teile.append("unbekannt: " + ", ".join(unbek))
    return {
        "key_mit": m.get("key_avg"),
        "key_ohne": o.get("key_avg"),
        "pref_mit": m.get("pref_avg"),
        "key_fehlt": len(fehlt) if keys else None,
        "key_n": len(bekannt) if keys else None,
        "key_unsicher": len(unsicher) if keys else None,
        "ausfaelle": "; ".join(teile),
    }


AUSFALL_ARTEN = ("fehlt", "unsicher", "unbekannt")


def ausfall_liste(
    attrs: dict[str, tuple] | None, d_mit: dict | None, d_ohne: dict | None, schwelle: float
) -> list[dict]:
    """Ausfälle des Rollenpaars strukturiert (für die Web-App), gleiche Regeln wie paar():
    art fehlt (Mitte < Schwelle), unsicher (lo < Schwelle <= Mitte) oder unbekannt; anzeige = Wert bzw. Spanne,
    phasen = Rollen (mit/ohne), zu denen das key-Attribut gehört. Reihenfolge: fehlt, unsicher, unbekannt."""
    attrs = attrs or {}
    phasen: dict[str, list[str]] = {}
    for ph, d in (("mit", d_mit), ("ohne", d_ohne)):
        for k in (d or {}).get("key") or []:
            phasen.setdefault(k, []).append(ph)
    out = []
    for k, ph in phasen.items():
        v = attrs.get(k, (None, None, None))
        m, lo = _mitte(v)
        if m is None:
            art = "unbekannt"
        elif m < schwelle:
            art = "fehlt"
        elif lo < schwelle:
            art = "unsicher"
        else:
            continue
        out.append({"attribut": k, "art": art, "anzeige": _fmt(v), "mitte": m, "exakt": _ok(v[0]),
                    "phasen": ph})  # fmt: skip
    return sorted(out, key=lambda e: AUSFALL_ARTEN.index(e["art"]))


def attribute_laden(
    conn, save: str, uids: Iterable, bevorzugt: dict | None = None
) -> tuple[dict[str, dict[str, tuple]], dict[str, str]]:
    """{uid: {Attribut: (Wert, lo, hi)}} und {uid: In-Game-Datum der Quelle}.

    Je Spieler der Snapshot aus `bevorzugt` (uid -> snapshot_id), falls er dort Attribute hat, sonst der neueste
    Snapshot des Saves mit Attributen."""
    uids = [str(u) for u in dict.fromkeys(uids) if _ok(u)]
    bevorzugt = {str(k): v for k, v in (bevorzugt or {}).items() if _ok(v)}
    rows = []
    for i in range(0, len(uids), 500):
        chunk = uids[i : i + 500]
        rows += conn.execute(
            "SELECT a.player_uid, a.snapshot_id, s.ingame_date, a.attribute, a.value, a.lo, a.hi "
            "FROM player_attributes a JOIN snapshots s ON s.id = a.snapshot_id "
            f"WHERE s.save = ? AND a.player_uid IN ({','.join('?' * len(chunk))})",
            [save, *chunk],
        ).fetchall()
    if not rows:
        return {}, {}
    t = pd.DataFrame(rows, columns=["uid", "sid", "datum", "attr", "wert", "lo", "hi"])
    snaps = t[["uid", "sid", "datum"]].drop_duplicates()
    snaps["pref"] = [bevorzugt.get(u) == s for u, s in zip(snaps["uid"], snaps["sid"], strict=True)]
    wahl = snaps.sort_values(["uid", "pref", "datum", "sid"]).drop_duplicates("uid", keep="last")
    t = t.merge(wahl[["uid", "sid"]], on=["uid", "sid"])
    out: dict[str, dict[str, tuple]] = {}
    for u, a, w, lo, hi in zip(t["uid"], t["attr"], t["wert"], t["lo"], t["hi"], strict=True):
        out.setdefault(u, {})[a] = (w, lo, hi)
    return out, dict(zip(wahl["uid"], wahl["datum"], strict=True))


SPALTEN = ["key_mit", "key_ohne", "pref_mit", "key_fehlt", "key_n", "key_unsicher", "ausfaelle"]


def spalten(
    df: pd.DataFrame, attrs: dict, d_mit: dict | None, d_ohne: dict | None, schwelle: float
):
    """DataFrame mit SPALTEN für die Zeilen von df (Index bleibt)."""
    recs = [paar(attrs.get(str(u)), d_mit, d_ohne, schwelle) for u in df["uid"]]
    return pd.DataFrame(recs, index=df.index, columns=SPALTEN)


def haeufigste_ausfaelle(attrs_list: Iterable[dict | None], d: dict | None, schwelle: float, top=3):
    """[(Attribut, Anteil verfehlt in %, n)] der key-Attribute einer Rolle über eine Spielermenge."""
    if d is None:
        return []
    zaehl: dict[str, list[int]] = {k: [0, 0] for k in d.get("key") or []}
    for attrs in attrs_list:
        if not attrs:
            continue
        for k, z in zaehl.items():
            m, _ = _mitte(attrs.get(k, (None, None, None)))
            if m is not None:
                z[1] += 1
                z[0] += m < schwelle
    res = [(k, 100 * f / n, n) for k, (f, n) in zaehl.items() if n]
    return sorted(res, key=lambda x: -x[1])[:top]
