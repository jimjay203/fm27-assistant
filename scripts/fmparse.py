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


def parse_number(s, decimal: str = ".") -> float | None:
    """'1.234,5' (decimal=',') bzw. '1,234.5' (decimal='.') -> 1234.5; '45%' -> 45.0."""
    t = _clean(s)
    if t is None:
        return None
    t = t.rstrip("%").strip().replace(" ", "")
    thousands = "," if decimal == "." else "."
    t = t.replace(thousands, "")
    if decimal == ",":
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _money_one(t: str, decimal: str) -> float | None:
    t = re.sub(r"[€$£]", "", t)
    t = re.sub(r"(p\.?\s*/?\s*[wma]\.?|pro\s+\w+)\s*$", "", t.strip(), flags=re.IGNORECASE).strip()
    m = re.fullmatch(r"([\d.,\s]+?)\s*(mio|mrd|tsd|k|m|b)?\.?", t, flags=re.IGNORECASE)
    if not m:
        return None
    num = parse_number(m.group(1), decimal)
    if num is None:
        return None
    return num * _MULT.get((m.group(2) or "").lower(), 1.0)


def parse_money(s, decimal: str = ".") -> float | None:
    """'€1.5M', '€250K', '1,5 Mio.' -> Euro. Bereiche ('€1M - €2M') -> Mittelwert."""
    t = _clean(s)
    if t is None:
        return None
    parts = re.split(r"\s+[-–]\s+|\s*–\s*", t)
    vals = [v for v in (_money_one(p, decimal) for p in parts) if v is not None]
    return sum(vals) / len(vals) if vals else None


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
