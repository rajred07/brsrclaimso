"""Explicit unit spellings and a small deterministic conversion table."""
import re
from decimal import Decimal, InvalidOperation


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing or invalid numeric operand")
    text = str(value).strip().replace("−", "-")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    # Only remove separators from numeric strings; never extract digits from prose.
    if not re.fullmatch(r"[+-]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        raise ValueError(f"Invalid numeric value: {value!r}")
    try:
        result = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric value") from exc
    if not result.is_finite():
        raise ValueError("Non-finite numeric value")
    return result


SPELLINGS = {
    "mj": "MJ", "megajoule": "MJ", "megajoules": "MJ",
    "tj": "TJ", "terajoule": "TJ", "terajoules": "TJ",
    "pj": "PJ", "petajoule": "PJ", "petajoules": "PJ",
    "millionlitres": "ML", "millionliters": "ML", "ml": "ML",
    "millionkilolitres": "millionkL", "millionkl": "millionkL",
    "kilotonnes": "kt", "kilotonne": "kt", "kt": "kt",
    "kilotonnesofco2equivalent": "ktCO2e", "ktco2e": "ktCO2e",
    "milliontonnesco2e": "milliontCO2e", "milliontco2e": "milliontCO2e",
    "gj-gigajoules": "GJ",
    "kl": "kL", "kilolitres": "kL", "kiloliters": "kL", "kilolitre": "kL",
    "l": "L", "litres": "L", "liters": "L", "litre": "L",
    "gj": "GJ", "gigajoule": "GJ", "gigajoules": "GJ",
    "mwh": "MWh", "kwh": "kWh",
    "tco2e": "tCO2e", "tonnesco2e": "tCO2e", "kgco2e": "kgCO2e",
    "metrictonnesofco2equivalent": "tCO2e",
    "t": "t", "tonne": "t", "tonnes": "t", "metrictonnes": "t",
    "count": "count", "number": "count", "numbers": "count",
    "%": "%", "percent": "%", "percentage": "%", "pure": "pure",
}
# family, multiplier to the canonical unit, canonical unit
TABLE = {
    "MJ": ("energy", Decimal("0.001"), "GJ"),
    "TJ": ("energy", Decimal("1000"), "GJ"),
    "PJ": ("energy", Decimal("1000000"), "GJ"),
    "ML": ("water", Decimal("1000000"), "L"),
    "millionkL": ("water", Decimal("1000000000"), "L"),
    "kt": ("waste", Decimal("1000"), "t"),
    "ktCO2e": ("emissions", Decimal("1000"), "tCO2e"),
    "milliontCO2e": ("emissions", Decimal("1000000"), "tCO2e"),
    "L": ("water", Decimal("1"), "L"),
    "kL": ("water", Decimal("1000"), "L"),
    "GJ": ("energy", Decimal("1"), "GJ"),
    "MWh": ("energy", Decimal("3.6"), "GJ"),
    "kWh": ("energy", Decimal("0.0036"), "GJ"),
    "tCO2e": ("emissions", Decimal("1"), "tCO2e"),
    "kgCO2e": ("emissions", Decimal("0.001"), "tCO2e"),
    "t": ("waste", Decimal("1"), "t"),
    "count": ("count", Decimal("1"), "count"),
    "%": ("percentage", Decimal("1"), "%"),
}


def canonical_unit(unit):
    if not unit:
        return None
    text = str(unit).strip()
    if "/" in text or "*" in text:
        return text  # compound/intensity units are not scalar totals
    text = text.rsplit(":", 1)[-1]
    # MtCO2e is deliberately NOT equated to tonnes: its meaning needs evidence.
    key = re.sub(r"[\s_]", "", text).casefold()
    return SPELLINGS.get(key, text)


def compatible(left, right):
    left, right = canonical_unit(left), canonical_unit(right)
    return bool(left in TABLE and right in TABLE and TABLE[left][0] == TABLE[right][0])


def normalize(value, unit):
    unit = canonical_unit(unit)
    if unit not in TABLE:
        raise ValueError(f"Unsupported or missing unit: {unit}")
    _, factor, normalized_unit = TABLE[unit]
    return number(value) * factor, normalized_unit


def convert(value, source, target):
    if not compatible(source, target):
        raise ValueError("UNIT_INCOMPATIBLE")
    normalized, _ = normalize(value, source)
    return normalized / TABLE[canonical_unit(target)][1]
