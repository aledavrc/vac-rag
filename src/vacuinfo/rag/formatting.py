from __future__ import annotations

import re


def _normalize_line(line: str) -> str:
    if line.lstrip().startswith("|"):
        return line.rstrip()
    return re.sub(r"[ \t]+", " ", line).rstrip()


def _split_inline_bullets(value: str) -> list[str] | None:
    """Detecta listas inline tipo '+ a + b' o '* a * b'."""

    for marker in ("+", "*"):
        pattern = re.compile(rf"\s*{re.escape(marker)}\s+")
        if len(pattern.findall(value)) < 2:
            continue
        items = [item.strip(" +*") for item in pattern.split(value) if item.strip(" +*")]
        if len(items) >= 2:
            return items
    return None


def _format_cell(cell: str) -> str:
    """Convierte listas inline de una celda en viñetas separadas por <br>."""

    items = _split_inline_bullets(cell)
    if items is None:
        return cell
    return "<br>".join(f"• {item}" for item in items)


def _format_table_row(line: str) -> str:
    if not line.lstrip().startswith("|"):
        return line
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = re.split(r"(?<!\\)\|", stripped)
    return "| " + " | ".join(_format_cell(cell.strip()) for cell in cells) + " |"


def _format_inline_bullets(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            lines.append(_format_table_row(line))
            continue
        if " — " in line:
            head, _, value = line.rpartition(" — ")
            items = _split_inline_bullets(value)
            if items is not None:
                lines.append(head + " —")
                lines.extend(f"- {item}" for item in items)
                continue
        lines.append(_normalize_line(line))
    return _ensure_table_separators(lines)


def _is_separator_row(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells)


def _ensure_table_separators(lines: list[str]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].lstrip().startswith("|"):
            result.append(lines[index])
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            block.append(lines[index])
            index += 1
        if len(block) >= 2 and not _is_separator_row(block[1]):
            columns = block[0].count("|") - 1
            result.append(block[0])
            result.append("|" + " --- |" * max(columns, 1))
            result.extend(block[1:])
        else:
            result.extend(block)
    return result


def format_chunk_markdown(text: str) -> str:
    """Conserva tablas y listas y mejora los listados dentro de celdas."""

    text = text.strip()
    if not text:
        return text
    text = "\n".join(_format_inline_bullets(text))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clip_markdown(text: str, limit: int = 1200) -> str:
    """Recorta sin destruir saltos de línea ni tablas."""

    text = format_chunk_markdown(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rstrip()
    if "\n" in cut:
        cut = cut.rsplit("\n", 1)[0]
    return cut.rstrip() + "..."
