from __future__ import annotations

import re

# --- Reparación de layout -------------------------------------------------
# Docling ya segmenta el layout, pero un OCR de página completa todavía puede
# dejar un encabezado de sección o una fila de tabla pegada al párrafo previo.

_SECTION_GLUED = re.compile(
    r"(?<=[.;:)\]%])\s+(?=\d+(?:\.\d+){2,}\.?\s+[A-ZÁÉÍÓÚÑ])"
)
_LIST_GLUED = re.compile(r"(?<=[.;:])\s+(?=[a-z]\)\s)")
_TABLE_GLUED = re.compile(r"(?<=[.;:])\s+(\|(?:[^|\n]+\|)+)\s*$", re.MULTILINE)


def _separate_tables(text: str) -> str:
    """Deja una línea en blanco antes y después de cada bloque de tabla."""

    text = re.sub(r"(?m)^([^|\n][^\n]*)\n(?=\|)", r"\1\n\n", text)
    text = re.sub(r"(?m)^(\|[^\n]*\|)\n(?=[^|\n])", r"\1\n\n", text)
    return text


def _outside_table(match: re.Match[str], replacement: str) -> str:
    """Aplica la reparación solo si el match no cae dentro de una fila de tabla."""

    line_start = match.string.rfind("\n", 0, match.start()) + 1
    line_end = match.string.find("\n", match.start())
    if line_end == -1:
        line_end = len(match.string)
    if match.string[line_start:line_end].lstrip().startswith("|"):
        return match.group(0)
    return replacement


def _separate_glued_table(match: re.Match[str]) -> str:
    line_start = match.string.rfind("\n", 0, match.start()) + 1
    if match.string[line_start : match.start()].lstrip().startswith("|"):
        return match.group(0)
    return "\n\n" + match.group(1)


def repair_markdown_layout(text: str) -> str:
    """Repara uniones de línea que el OCR aplanó, sin tocar el contenido."""

    text = _SECTION_GLUED.sub(lambda match: _outside_table(match, "\n\n"), text)
    text = _LIST_GLUED.sub(lambda match: _outside_table(match, "\n"), text)
    text = _TABLE_GLUED.sub(_separate_glued_table, text)
    return _separate_tables(text)


# --- Léxico del dominio (NTS 246 / MINSA) --------------------------------
# Solo variantes inequívocas observadas en el corpus. No se capitalizan
# palabras sueltas ni se completan datos clínicos.

_TERM_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bHVB\b"), "HvB"),
    (re.compile(r"\bHvb\b"), "HvB"),
    (re.compile(r"\bVHP\b"), "VPH"),
    (re.compile(r"\bVP\s*H\b"), "VPH"),
    (re.compile(r"\bESAVIS\b"), "ESAVI"),
    (re.compile(r"\bDTP\b"), "DPT"),
    (re.compile(r"\bTdpa\b"), "Tdap"),
    (re.compile(r"\bTdaP\b"), "Tdap"),
    # El OCR confunde el numeral romano I con 1/l en la cepa de BCG.
    (re.compile(r"\b(Moscow)\s+361\s*[-–]\s*[1lI]\b", re.IGNORECASE), "Moscow 361-I"),
)


def canonicalize_terms(text: str) -> str:
    for pattern, replacement in _TERM_FIXES:
        text = pattern.sub(replacement, text)
    return text


# --- Notación científica ------------------------------------------------
# El OCR de una página escaneada pierde el superíndice: "1 X 105" es 1 × 10⁵.
# Solo se corrige cuando hay una multiplicación explícita por 10, para no
# tocar números como "105" o "1 × 100".
_SUPERSCRIPT = {"5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"}
_SCIENTIFIC_PLAIN = re.compile(
    r"(?P<coef>\d+(?:[.,]\d+)?)\s*[x×X]\s*10\s*\^?\s*(?P<exp>[5-9])\b(?![.,]\d)"
)
_SCIENTIFIC_SUPERSCRIPT = re.compile(
    r"(?P<coef>\d+(?:[.,]\d+)?)\s*[x×X]\s*10(?P<exp>[⁵⁶⁷⁸⁹])"
)


def normalize_scientific_notation(text: str) -> str:
    """Restituye el exponente perdido cuando el OCR dejó "x 105"."""

    def plain(match: re.Match[str]) -> str:
        exponent = _SUPERSCRIPT[match.group("exp")]
        return f"{match.group('coef')} × 10{exponent}"

    def superscript(match: re.Match[str]) -> str:
        return f"{match.group('coef')} × 10{match.group('exp')}"

    text = _SCIENTIFIC_SUPERSCRIPT.sub(superscript, text)
    return _SCIENTIFIC_PLAIN.sub(plain, text)


# --- Ordinales de dosis ---------------------------------------------------
# El OCR confunde "1ra" con "lra"/"1.a"/"1ª" y "2da" con "2da.".

_DOSE_ORDINAL = re.compile(
    r"\b(?P<num>[1-4l])\s*(?P<suf>ra|da|ta|era|ª|\.a|°a)\b\.?"
)
_REFUERZO_ORDINAL = re.compile(r"\b(?P<num>[1-4])\s*(?P<suf>er|do|ro|to)\b\.?")
_DOSE_WORD = re.compile(r"\s*dosis\b", re.IGNORECASE)
_DOSE_SUFFIX = {
    "ra": "ra",
    "era": "ra",
    "ª": "ra",
    ".a": "ra",
    "°a": "ra",
    "da": "da",
    "ta": "ta",
}
_REFUERZO_SUFFIX = {"er": "er", "do": "do", "ro": "ro", "to": "to"}


def normalize_dose_ordinals(text: str) -> str:
    """Canoniza ordinales de dosis y refuerzos sin duplicar "dosis"."""

    def dose(match: re.Match[str]) -> str:
        num = "1" if match.group("num").lower() in {"l", "i"} else match.group("num")
        suffix = _DOSE_SUFFIX[match.group("suf").lower()]
        ordinal = f"{num}{suffix}"
        if _DOSE_WORD.match(text, match.end()):
            return ordinal
        return f"{ordinal} dosis"

    def refuerzo(match: re.Match[str]) -> str:
        return f"{match.group('num')}{_REFUERZO_SUFFIX[match.group('suf').lower()]}"

    text = _REFUERZO_ORDINAL.sub(refuerzo, text)
    return _DOSE_ORDINAL.sub(dose, text)
