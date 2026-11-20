"""Parser für FM-Exportformate (Geld, Zahlen, Attributbereiche, Datum).

Dezimaltrenner ist konfigurierbar (spalten.yaml -> zahlenformat.dezimal), damit keine
Heuristik "1.234" (Tausender oder Dezimal?) nötig ist. TODO(export): Format des echten Exports prüfen.
"""

from __future__ import annotations

import re
from datetime import datetime

_NULLS = {"", "-", "–", "—", "?", "n/a", "nan", "none", "null"}
_MULT = {"k": 1e3, "tsd": 1e3, "m": 1e6, "mio": 1e6, "b": 1e9, "mrd": 1e9}
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d.%m.%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%b %d, %Y",
)


def _clean(s) -> str | None:
    if s is None:
        return None
    t = str(s).replace(" ", " ").replace("−", "-").strip()
    return None if t.lower() in _NULLS else t


def is_null(s) -> bool:
    return _clean(s) is None


def parse_number(s, decimal: str = ".", einheit: str | None = None) -> float | None:
    """'1.234,5' (decimal=',') bzw. '1,234.5' (decimal='.') -> 1234.5; '45%' -> 45.0.

    `einheit` ('km'): Pflicht-Suffix, wird abgeschnitten; fehlt sie -> None. Ein Tausendertrenner
    ist nur in korrekter Gruppierung (1.234) erlaubt; '2.01' bei decimal=',' ist daher None statt 201.
    """
    t = _clean(s)
    if t is None:
        return None
    if einheit:
        if not t.lower().endswith(einheit.lower()):
            return None
        t = t[: -len(einheit)]
    t = t.rstrip("%").strip().replace(" ", "")
    thousands = "," if decimal == "." else "."
    if thousands in t and not re.fullmatch(
        rf"-?\d{{1,3}}(?:{re.escape(thousands)}\d{{3}})+(?:{re.escape(decimal)}\d+)?", t
    ):
        return None
    t = t.replace(thousands, "")
    if decimal == ",":
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _money_one(t: str, decimal: str) -> float | None:
    t = re.sub(r"[€$£]", "", t)
    t = re.sub(
        r"(p\.?\s*/?\s*[wma]\.?|pro\s+\w+|/\s*(?:jahr|j|monat|mon|woche|wo)\.?)\s*$",
        "",
        t.strip(),
        flags=re.IGNORECASE,
    ).strip()
    m = re.fullmatch(r"([\d.,\s]+?)\s*(mio|mrd|tsd|k|m|b)?\.?", t, flags=re.IGNORECASE)
    if not m:
        return None
    num = parse_number(m.group(1), decimal)
    if num is None:
        return None
    return num * _MULT.get((m.group(2) or "").lower(), 1.0)


def _money_parts(s, decimal: str) -> list[float]:
    t = _clean(s)
    if t is None:
        return []
    parts = re.split(r"\s+[-–]\s+|\s*–\s*", t)
    return [v for v in (_money_one(p, decimal) for p in parts) if v is not None]


def parse_money(s, decimal: str = ".") -> float | None:
    """'€1.5M', '€250K', '1,5 Mio.', '997K €/J.' -> Euro. Bereiche ('€1M - €2M') -> Mittelwert."""
    vals = _money_parts(s, decimal)
    return sum(vals) / len(vals) if vals else None


def parse_money_range(s, decimal: str = ".") -> tuple[float, float] | None:
    """'9Mio. € - 11,5Mio. €' -> (9e6, 11.5e6); Einzelwert -> (v, v); Text ('Steht nicht ...') -> None."""
    vals = _money_parts(s, decimal)
    return (min(vals), max(vals)) if vals else None


_PERIODS = {"j": "jahr", "jahr": "jahr", "a": "jahr", "mon": "monat", "monat": "monat",
            "m": "monat", "wo": "woche", "woche": "woche", "w": "woche"}  # fmt: skip


def money_period(s) -> str | None:
    """Zeitbezug eines Geldwerts: '€/J.' -> 'jahr', 'p/w' -> 'woche', sonst None."""
    t = _clean(s)
    m = re.search(r"(?:/|\bp\.?\s*/?\s*)(jahr|j|monat|mon|m|woche|wo|w|a)\.?\s*$", t or "", re.I)
    return _PERIODS[m.group(1).lower()] if m else None


def parse_apps(s) -> tuple[int, int] | None:
    """Einsätze '6 (2)' -> (6 Starts, 2 Einwechslungen); '6' -> (6, 0)."""
    t = _clean(s)
    m = re.fullmatch(r"(\d+)(?:\s*\((\d+)\))?", t or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def parse_attribute(s, decimal: str = ".") -> tuple[float | None, bool]:
    """-> (wert, maskiert). Bereiche ('12-15') und unbekannte Werte sind maskiert (NULL)."""
    t = _clean(s)
    if t is None:
        return None, True
    if re.fullmatch(r"\d+\s*[-–]\s*\d+", t):
        return None, True
    v = parse_number(t, decimal)
    return (v, False) if v is not None else (None, True)


def parse_date(s) -> str | None:
    t = _clean(s)
    if t is None:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def to_annual(amount: float | None, period: str) -> float | None:
    if amount is None:
        return None
    factor = {"woche": 52, "monat": 12, "jahr": 1}[period]
    return amount * factor
