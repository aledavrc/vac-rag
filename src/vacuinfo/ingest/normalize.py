from __future__ import annotations

import re

from vacuinfo.ingest.lexicon import normalize_dose_ordinals, normalize_scientific_notation

_DECIMAL_VOLUME = re.compile(
    r"\b(?P<int>[Oo]|\d+)?\s*[.,]\s*(?P<dec>\d+)\s*"
    r"(?P<unit>ml|m1|mi|mL|ML|mI|mí|ma)\b",
    re.IGNORECASE,
)
_ML = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:ml|mL|ML|mI|mí|mi|m1|ma|má)\b",
    re.IGNORECASE,
)
_ML_DECIMAL_MIL = re.compile(r"(?P<num>\d+[.,]\d+)\s*mil\b", re.IGNORECASE)
_MCG = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?:mcg|mcg\.?|ug|µg|μg)\b",
    re.IGNORECASE,
)

# Rango de cadena de frío con el símbolo de grado perdido o cambiado:
# "+20C a +80C", "+2 oC a +8 oC", "2°C a 8°C", "+2'Ca+8%C".
_TEMP_RANGE = re.compile(
    r"(?P<asign>[+-])?\s*(?P<a>\d{1,2})\s*"
    r"(?:[°ºoO%'’\"*]\s*C?|C)\s*[aA]?\s*"
    r"(?P<bsign>[+-])?\s*(?P<b>\d{1,2})\s*"
    r"(?:[°ºoO%'’\"*]\s*C?|C)\b"
)
# Símbolo presente pero corrupto: "+2 oC", "+8%C", "+2'C", "+ 2°C".
_TEMP_MARK = re.compile(
    r"(?P<sign>[+-])?\s*(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?:°|º|o|O|%|'|’|\"|\*)\s*C(?P<a>[aA])?(?=\s|$|[,.;:)+])"
)
# Símbolo de grado perdido del todo: "+20C" / "+80C".
_TEMP_COMPACT = re.compile(r"(?P<sign>[+])\s*(?P<num>20|80)\s*C\b")
_COLD_CONTEXT = re.compile(
    r"conserv|frasco|refriger|cadena|fr[ií]o|temperatura|nevera|termo",
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

_COLD_DIGITS = {20: 2, 80: 8}
_COLD_ENDPOINTS = {2, 8, 20, 80}


def _decimal_volume(match: re.Match[str]) -> str:
    """Corrige O/0 inicial y coma decimal en volúmenes pequeños."""

    integer = match.group("int") or "0"
    if integer in {"O", "o"}:
        integer = "0"
    if integer == "0":
        separator = "."
    else:
        separator = "," if "," in match.group(0) else "."
    return f"{integer}{separator}{match.group('dec')} ml"


def _replace_unit(match: re.Match[str], unit: str) -> str:
    return f"{match.group('num')} {unit}"


def _normalize_range(match: re.Match[str]) -> str:
    left, right = match.group("a"), match.group("b")
    left_int, right_int = int(left), int(right)
    left_negative = match.group("asign") == "-"
    right_negative = match.group("bsign") == "-"

    if not left_negative and not right_negative and left_int > 0 and right_int > 0:
        if left_int in _COLD_DIGITS and (
            right_int in _COLD_ENDPOINTS or right_int in {2, 8}
        ):
            left_int = _COLD_DIGITS[left_int]
        if right_int in _COLD_DIGITS and (
            left_int in _COLD_ENDPOINTS or left_int in {2, 8}
        ):
            right_int = _COLD_DIGITS[right_int]

    def render(negative: bool, number: int) -> str:
        sign = "-" if negative else ("+" if number > 0 else "")
        return f"{sign}{number} °C"

    return f"{render(left_negative, left_int)} a {render(right_negative, right_int)}"


def _normalize_compact_temperatures(text: str, flags: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        start = max(0, match.start() - 120)
        context = text[start : match.end() + 120]
        if _COLD_CONTEXT.search(context):
            return f"+{_COLD_DIGITS[int(match.group('num'))]} °C"
        flags.append(f"temperatura dudosa: {match.group(0)}")
        return match.group(0)

    return _TEMP_COMPACT.sub(replace, text)


def _replace_temperature(match: re.Match[str]) -> str:
    suffix = " a" if match.group("a") else ""
    sign = match.group("sign") or ""
    return f"{sign}{match.group('num')} °C{suffix}"


def normalize_clinical_text(text: str) -> tuple[str, list[str]]:
    """Normaliza unidades dudosas y marca valores que requieren revisión.

    No intenta adivinar puntos decimales perdidos sin separador: esos casos se
    marcan para revisión manual. El léxico del dominio se aplica antes, en
    `clean_page_markdown`.
    """

    flags: list[str] = []

    # Símbolos Unicode de temperatura y duplicados del OCR: ℃, °℃, °°C.
    text = text.replace("℃", "°C").replace("℉", "°F")
    text = re.sub(r"°\s*°\s*C", "°C", text)
    text = normalize_scientific_notation(text)

    text = _TEMP_RANGE.sub(_normalize_range, text)
    text = _normalize_compact_temperatures(text, flags)
    text = _TEMP_MARK.sub(_replace_temperature, text)

    text = _DECIMAL_VOLUME.sub(_decimal_volume, text)
    text = _ML.sub(lambda match: _replace_unit(match, "ml"), text)
    text = _ML_DECIMAL_MIL.sub(lambda match: _replace_unit(match, "ml"), text)
    text = _MCG.sub(lambda match: _replace_unit(match, "mcg"), text)

    text = normalize_dose_ordinals(text)

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
