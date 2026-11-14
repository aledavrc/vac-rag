from __future__ import annotations

import re
import unicodedata
from collections import Counter

from vacuinfo.ingest.lexicon import canonicalize_terms, repair_markdown_layout

_HEADER_PATTERNS = (
    re.compile(r"MINS\w*\s*/?\s*DGIESP", re.IGNORECASE),
    re.compile(r"MINSA\w*[^\n]{0,40}20\d{2}", re.IGNORECASE),
    re.compile(r"DGIESP.*(NORMA|NTS)|(NORMA|NTS).*DGIESP", re.IGNORECASE),
    re.compile(r"^\s*NORMA\s+T[EÉ]CNICA\s+DE\s+SALUD", re.IGNORECASE),
    re.compile(r"^\s*NTS\s*N[°º]?\s*246", re.IGNORECASE),
    re.compile(r"^\s*NTSN", re.IGNORECASE),
)

_SEAL_PATTERNS = (
    re.compile(r"COLEGIO\s+M[EÉ]DICO", re.IGNORECASE),
    re.compile(r"^\s*(CMP|DNI|FIRMA|SELLO|PER[UÚ])\s*$", re.IGNORECASE),
)

_PAGE_NUMBER = re.compile(r"^\s*\d{1,3}\s*$")
_IMAGE_PLACEHOLDER = re.compile(r"^\s*<!--\s*image\s*-->\s*$", re.IGNORECASE)
_DOTS_ONLY = re.compile(r"^[.\s·…]+$")
_TABLE_LINE = re.compile(r"^\s*\|")
_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


def is_header_noise_line(text: str) -> bool:
    """Indica si una línea parece encabezado/pie repetido del escaneo."""

    stripped = re.sub(r"^#{1,6}\s*", "", text.strip())
    return any(pattern.search(stripped) for pattern in _HEADER_PATTERNS)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00ad", "")  # guion blando
    text = text.replace("\u00a0", " ").replace("\t", " ")
    text = text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    text = text.replace("`", "'")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_for_match(text: str) -> str:
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9áéíóúñü/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def line_key(line: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(line)).strip().lower()


def _is_noise_line(line: str, *, in_table: bool) -> bool:
    stripped = re.sub(r"^#{1,6}\s*", "", line.strip())
    if not stripped:
        return False
    if _IMAGE_PLACEHOLDER.match(stripped) or _DOTS_ONLY.match(stripped):
        return True
    if any(pattern.search(stripped) for pattern in _HEADER_PATTERNS):
        return True
    if any(pattern.search(stripped) for pattern in _SEAL_PATTERNS):
        return True
    if not in_table and _PAGE_NUMBER.match(stripped):
        return True
    return False


def _dehyphenate(text: str) -> str:
    return re.sub(r"(?<=[a-záéíóúñü])-\s*\n\s*(?=[a-záéíóúñü])", "", text)


def detect_repeated_edge_lines(
    pages: list[str], *, edge: int = 4, min_ratio: float = 0.2
) -> set[str]:
    """Detecta encabezados/pies repetidos mirando solo los bordes de cada página.

    No se miran líneas del cuerpo para no borrar contenidos legítimos que se
    repiten en varias fichas (por ejemplo, referencias a anexos).
    """

    counter: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        candidates = set(lines[:edge] + lines[-edge:])
        for line in candidates:
            if line.startswith("|") or len(line) < 4:
                continue
            counter[line_key(line)] += 1

    threshold = max(2, int(len(pages) * min_ratio))
    return {key for key, count in counter.items() if count >= threshold}


def clean_page_markdown(text: str, repeated_lines: set[str] | None = None) -> str:
    repeated_lines = repeated_lines or set()
    text = normalize_text(text)
    text = _dehyphenate(text)
    text = repair_markdown_layout(text)
    text = canonicalize_terms(text)

    lines = text.splitlines()
    last_content = max((i for i, line in enumerate(lines) if line.strip()), default=-1)
    cleaned: list[str] = []
    in_table = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        in_table = bool(_TABLE_LINE.match(line))

        if _is_noise_line(line, in_table=in_table):
            continue

        near_edge = index < 4 or index > last_content - 4
        if near_edge and stripped and line_key(stripped) in repeated_lines:
            continue

        cleaned.append(line.rstrip())

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def is_table_line(line: str) -> bool:
    return bool(_TABLE_LINE.match(line))


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.match(cell.strip()) for cell in cells)


def split_table_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    cells = re.split(r"(?<!\\)\|", value)
    return [
        cell.replace("\\|", "|").replace("&#124;", "|").strip().strip("|").strip()
        for cell in cells
    ]


def parse_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        cells = split_table_row(line)
        if is_separator_row(cells):
            continue
        if any(cell for cell in cells):
            rows.append(cells)
    return rows


def looks_like_header(cells: list[str]) -> bool:
    """Heurística conservadora para distinguir una fila de encabezado."""

    if not cells:
        return False
    joined = " ".join(cells)
    words = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", joined)
    if not words:
        return False
    uppercase = sum(1 for word in words if word.isupper() and len(word) > 2)
    known = {
        "vacuna",
        "evento",
        "enfermedad",
        "tipo",
        "descripción",
        "descripcion",
        "dosis",
        "edad",
        "intervalo",
        "tiempo",
        "tasa",
        "error",
        "consecuencia",
        "grupo",
        "población",
        "poblacion",
    }
    normalized = {strip_accents(word).lower() for word in words}
    return uppercase / len(words) >= 0.5 or len(normalized & known) >= 3
