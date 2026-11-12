from __future__ import annotations

import re

_ML = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:ml|mL|ML|mI|mí|mi|m1|ma|má)\b",
    re.IGNORECASE,
)
_ML_DECIMAL_MIL = re.compile(r"(?P<num>\d+[.,]\d+)\s*mil\b", re.IGNORECASE)
_MCG = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:mcg|mcg\.?|ug|µg|μg)\b",
    re.IGNORECASE,
)
_TEMP_QUOTE = re.compile(
    r"(?P<num>[+-]?\d+(?:[.,]\d+)?)\s*(?:°|º|'|’|\"|\*)\s*C(?P<a>[aA])?"
    r"(?=\s|$|[,.;:)+])",
    re.IGNORECASE,
)
_TEMP_PERCENT = re.compile(
    r"(?P<num>[+-]?\d+(?:[.,]\d+)?)\s*%\s*C\b",
    re.IGNORECASE,
)
_TEMP_STAR_A = re.compile(
    r"(?P<num>[+-]?\d+(?:[.,]\d+)?)\s*\*\s*[aA]\b",
    re.IGNORECASE,
)
_MISSING_DECIMAL = re.compile(
    r"(?<![\d.,])(?:[O0]\d{1,3})(?=\s*(?:ml|mi|mí|mI|m1|ma|mcg|mg|g|gotas)\b)",
    re.IGNORECASE,
)
_DOSIS_FIELD = re.compile(
    r"DOSIS\s*\(CANTIDAD\)\s*:\s*(?P<val>[^\n]{0,100})",
    re.IGNORECASE,
)


def _replace_unit(match: re.Match[str], unit: str) -> str:
    return f"{match.group('num')} {unit}"


def _replace_temperature(match: re.Match[str]) -> str:
    suffix = " a" if match.group("a") else ""
    return f"{match.group('num')} °C{suffix}"


def normalize_clinical_text(text: str) -> tuple[str, list[str]]:
    """Normaliza unidades dudosas y marca valores que requieren revisión.

    No intenta adivinar puntos decimales perdidos: esos casos se marcan para
    revisión manual.
    """

    flags: list[str] = []

    text = _ML.sub(lambda match: _replace_unit(match, "ml"), text)
    text = _ML_DECIMAL_MIL.sub(lambda match: _replace_unit(match, "ml"), text)
    text = _MCG.sub(lambda match: _replace_unit(match, "mcg"), text)
    text = _TEMP_QUOTE.sub(_replace_temperature, text)
    text = _TEMP_PERCENT.sub(lambda match: _replace_unit(match, "°C"), text)
    text = _TEMP_STAR_A.sub(lambda match: f"{match.group('num')} °C a", text)

    if re.search(r"\d\s*(?:mi|mí|mI|m1)\b", text, re.IGNORECASE):
        flags.append("unidad ml dudosa")

    field = _DOSIS_FIELD.search(text)
    if field:
        value = field.group("val")
        has_number = bool(re.search(r"\d", value))
        has_unit = bool(
            re.search(r"\d\s*(?:ml|mcg|mg|g|gotas|dosis|tabletas?)\b", value, re.IGNORECASE)
        )
        if re.fullmatch(r"\s*[O0]\d{1,3}\s*", value):
            flags.append(f"posible decimal perdido: {value.strip()}")
        elif not has_number or (not has_unit and len(value.strip()) <= 30):
            flags.append("dosis con formato dudoso")

    for match in _MISSING_DECIMAL.finditer(text):
        token = match.group(0)
        flags.append(f"posible decimal perdido: {token}")

    # Elimina duplicados conservando el orden.
    unique_flags = list(dict.fromkeys(flags))
    return text, unique_flags
