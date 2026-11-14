from __future__ import annotations

import re

from vacuinfo.ingest.clean import is_separator_row, normalize_for_match, split_table_row

_HEADING = re.compile(
    r"^(?:#{1,6}\s+\S|\d+(?:\.\d+){1,}\.?\s+[A-ZÁÉÍÓÚÑ]|ANEXO\s+\d+\b)",
    re.IGNORECASE,
)
# Llamadas de nota al pie: "(1)", "( *)", "1.", "Nota:", "* ...".
_TABLE_NOTE = re.compile(
    r"^\s*(?:\(\s*(?:\d+|[a-zA-Z]\*?|\*)\s*\)|(?:\d+)[.)]\s+|\*+\s+|Nota\b|NOTA\b)",
    re.IGNORECASE,
)
_CLOSING_PUNCTUATION = re.compile(r"[.:;!?)]\s*$")


def split_blocks(text: str) -> list[str]:
    """Separa Markdown en bloques por línea en blanco, conservando su orden."""

    return [block.strip("\n") for block in re.split(r"\n\s*\n", text) if block.strip()]


def block_kind(block: str) -> str:
    first = block.lstrip().splitlines()[0] if block.strip() else ""
    if first.lstrip().startswith("|"):
        return "table"
    if _HEADING.match(first.lstrip()):
        return "heading"
    return "text"


def _table_lines(block: str) -> list[str]:
    return [line.rstrip() for line in block.splitlines() if line.lstrip().startswith("|")]


def _table_width(block: str) -> int:
    rows = _table_lines(block)
    if not rows:
        return 0
    return max(len(split_table_row(line)) for line in rows)


def _table_header(block: str) -> list[str] | None:
    rows = _table_lines(block)
    if not rows:
        return None
    cells = split_table_row(rows[0])
    if is_separator_row(cells):
        return None
    return [normalize_for_match(cell) for cell in cells]


def _is_new_ficha(block: str) -> bool:
    rows = _table_lines(block)
    if not rows:
        return False
    cells = split_table_row(rows[0])
    if not cells:
        return False
    first = normalize_for_match(cells[0])
    return (
        first == "tipo de vacuna"
        or "tipo de vacuna" in first
        or bool(re.search(r"\b6\s*\.\s*1\s*\.\s*1\s*\.\s*\d+", cells[0]))
    )


def is_table_note(block: str) -> bool:
    return block_kind(block) == "text" and bool(_TABLE_NOTE.match(block.strip()))


def _is_ficha_table(block: str) -> bool:
    """Detecta una ficha key-value (no se fusiona moviendo filas de página).

    Las fichas se fusionan a nivel de campo en `chunk.py` (ADR-006) para no
    perder la página exacta de cada valor. Aquí solo se fusionan tablas
    multicolumna de anexos y esquemas.
    """

    from vacuinfo.ingest.chunk import KNOWN_FIELDS

    known = {normalize_for_match(field) for field in KNOWN_FIELDS}
    labels = []
    for line in _table_lines(block):
        cells = split_table_row(line)
        if cells and cells[0].strip():
            labels.append(normalize_for_match(cells[0]))
    hits = sum(1 for label in labels if label in known)
    return hits >= 2


def _starts_new_ficha_row(cells: list[str]) -> bool:
    if not cells:
        return False
    first = normalize_for_match(cells[0])
    return "tipo de vacuna" in first or bool(
        re.search(r"\b6\s*\.\s*1\s*\.\s*1\s*\.\s*\d+", cells[0])
    )


def _merge_tables(previous: str, nxt: str) -> tuple[str, str]:
    """Une dos tablas y elimina la fila de encabezado repetida de la segunda.

    Si la tabla siguiente contiene una ficha nueva a mitad de bloque, se corta
    ahí: la parte de continuación se fusiona y el resto permanece en su página
    para no perder la trazabilidad.
    """

    left = _table_lines(previous)
    right = _table_lines(nxt)
    header = _table_header(previous)
    merged = list(left)
    tail: list[str] = []
    in_tail = False

    for line in right:
        cells = split_table_row(line)
        normalized = [normalize_for_match(cell) for cell in cells]
        if is_separator_row(cells):
            if in_tail:
                tail.append(line)
            continue
        if header is not None and normalized == header:
            header = None  # solo se descarta la primera repetición
            continue
        if not in_tail and _starts_new_ficha_row(cells):
            in_tail = True
        if in_tail:
            tail.append(line)
        else:
            merged.append(line)
    return "\n".join(merged), "\n".join(tail)


def _join_paragraph(previous: str, nxt: str) -> str:
    left = previous.rstrip()
    if left.endswith("-"):
        left = left[:-1]
    return f"{left} {nxt.lstrip()}"


def merge_page_pair(
    previous: str, nxt: str
) -> tuple[str, str, dict[str, bool]]:
    """Fusiona el borde entre dos páginas consecutivas.

    Devuelve el texto de ambas páginas; el contenido fusionado queda en la
    página de inicio para conservar la trazabilidad del metadato `pagina`.
    """

    events = {"tabla": False, "nota": False, "parrafo": False}
    left_blocks = split_blocks(previous)
    right_blocks = split_blocks(nxt)
    if not left_blocks or not right_blocks:
        return previous, nxt, events

    last = left_blocks[-1]
    first = right_blocks[0]

    if block_kind(last) == "table" and block_kind(first) == "table":
        header_left = _table_header(last)
        header_right = _table_header(first)
        same_header = (
            header_left is not None
            and header_left == header_right
            and "tipo de vacuna" in header_left
        )
        if (
            _table_width(last) == _table_width(first)
            and _table_width(last) > 0
            and not _is_ficha_table(last)
            and not _is_ficha_table(first)
            and (not _is_new_ficha(first) or same_header)
        ):
            merged_table, tail_table = _merge_tables(last, first)
            left_blocks[-1] = merged_table
            if tail_table:
                right_blocks[0] = tail_table
            else:
                right_blocks.pop(0)
            events["tabla"] = True

    # Las notas al pie al inicio de la página siguiente pertenecen a la tabla
    # que termina en la página anterior.
    if not events["tabla"] and block_kind(last) == "table" and is_table_note(first):
        right_blocks.pop(0)
        left_blocks.append(first.strip())
        events["nota"] = True

    if events["tabla"]:
        while right_blocks and is_table_note(right_blocks[0]):
            left_blocks.append(right_blocks.pop(0).strip())
            events["nota"] = True

    if (
        not events["tabla"]
        and not events["nota"]
        and block_kind(left_blocks[-1]) == "text"
        and right_blocks
        and block_kind(right_blocks[0]) == "text"
        and not _CLOSING_PUNCTUATION.search(left_blocks[-1])
        and len(left_blocks[-1]) >= 30
    ):
        left_blocks[-1] = _join_paragraph(left_blocks[-1], right_blocks.pop(0))
        events["parrafo"] = True

    return "\n\n".join(left_blocks), "\n\n".join(right_blocks), events


def merge_pages(
    pages: list[str], *, skip: set[int] | None = None
) -> tuple[list[str], list[dict]]:
    """Fusiona tablas, notas y párrafos cortados entre páginas consecutivas.

    `skip` contiene páginas (1-based) que no deben participar en la fusión,
    como los formularios en blanco de los anexos.
    """

    skip = skip or set()
    merged = list(pages)
    reports: list[dict] = []
    for index in range(len(merged) - 1):
        page = index + 1
        if page in skip or page + 1 in skip:
            continue
        before = merged[index]
        after = merged[index + 1]
        merged[index], merged[index + 1], events = merge_page_pair(before, after)
        if any(events.values()):
            reports.append({"pagina": page, "pagina_fin": page + 1, **events})
    return merged, reports
