from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from difflib import get_close_matches
from pathlib import Path

from vacuinfo.config import DOC_TITLE, DocumentSpec, Settings
from vacuinfo.ingest.clean import (
    clean_page_markdown,
    detect_repeated_edge_lines,
    is_table_line,
    looks_like_header,
    normalize_for_match,
    parse_table,
)
from vacuinfo.ingest.normalize import normalize_clinical_text

VACCINE_ALIASES: dict[str, tuple[str, ...]] = {
    "BCG": ("bcg",),
    "Hepatitis B": ("hepatitis b", "hvb", "hepatitis virica b"),
    "Hib": ("hib", "haemophilus", "hemofilo"),
    "SPR": ("spr", "sarampion", "paperas", "rubeola", "antisarampionosa"),
    "APO/VOP": (
        "antipoliomielitica",
        "antipoliomielitis",
        "antipolio",
        "poliovirus",
        "apo",
        "vop",
        "sabin",
        "polio",
    ),
    "DTP": ("dtp", "dpt", "difteria", "tos ferina", "pertussis", "tdap"),
    "TT/DT": ("tt dt", "toxoide tetanico", "toxoide difterico", "td"),
    "Rotavirus": ("rotavirus",),
    "Neumococo": ("neumococo", "neumococica", "antineumococica"),
    "VPH": ("vph", "papiloma"),
    "Influenza": ("influenza", "gripe", "antigripal"),
    "Fiebre amarilla": ("fiebre amarilla", "antiamarilica"),
    "Rabia": ("rabia", "antirrabica"),
    "Varicela": ("varicela",),
    "Hepatitis A": ("hepatitis a", "hva"),
}

KNOWN_FIELDS = (
    "TIPO DE VACUNA",
    "DESCRIPCIÓN",
    "COMPOSICIÓN",
    "PRESENTACIÓN",
    "INDICACIÓN",
    "ESQUEMA DE VACUNACIÓN",
    "DOSIS (CANTIDAD)",
    "CONSERVACIÓN DE LA VACUNA",
    "VÍA Y SITIO DE ADMINISTRACIÓN",
    "JERINGAS A UTILIZAR",
    "POSIBLES EFECTOS POST-VACUNALES",
    "CONTRAINDICACIÓN",
    "USO SIMULTÁNEO CON OTRAS VACUNAS",
)
_KNOWN_BY_NORMALIZED = {normalize_for_match(field): field for field in KNOWN_FIELDS}
_OCR_FIELD_FIXES = {"ion": "INDICACIÓN"}

# Formularios y registros en blanco de los anexos: no aportan respuestas y
# generan mucho ruido de OCR.
SKIP_PRINTED_PAGES = frozenset({101, 102, 103, *range(121, 131), *range(131, 140)})


def normalize_field_name(key: str) -> str:
    """Corrige etiquetas de ficha mal OCR sin tocar el contenido clínico."""

    cleaned = re.sub(r"[|\s]+", " ", key).strip(" []").strip()
    if not cleaned:
        return "Continuación"
    normalized = normalize_for_match(cleaned)
    if normalized in _OCR_FIELD_FIXES:
        return _OCR_FIELD_FIXES[normalized]
    if normalized in _KNOWN_BY_NORMALIZED:
        return _KNOWN_BY_NORMALIZED[normalized]
    for candidate, display in _KNOWN_BY_NORMALIZED.items():
        if len(normalized) >= 5 and candidate.endswith(normalized):
            return display
    match = get_close_matches(normalized, _KNOWN_BY_NORMALIZED, n=1, cutoff=0.82)
    return _KNOWN_BY_NORMALIZED[match[0]] if match else cleaned


def detect_vaccine(text: str) -> str | None:
    normalized = f" {normalize_for_match(text)} "
    best: tuple[int, str] | None = None
    for canonical, aliases in VACCINE_ALIASES.items():
        for alias in aliases:
            needle = f" {alias} "
            position = normalized.find(needle)
            if position >= 0:
                candidate = (position, canonical)
                if best is None or candidate[0] < best[0]:
                    best = candidate
    return best[1] if best else None


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", line.strip()))


def _clean_heading(line: str) -> str:
    heading = re.sub(r"^#{1,6}\s+", "", line.strip())
    heading = re.sub(r"\s+", " ", heading).strip(" .:;")
    return heading


def _update_section(section: str, heading: str) -> str:
    heading = _clean_heading(heading)
    if not heading:
        return section
    if re.fullmatch(r"ANEXO\s+\d+", section, re.IGNORECASE) and not heading.upper().startswith(
        "ANEXO"
    ):
        return f"{section} — {heading}"
    return heading


def _iter_blocks(text: str) -> Iterator[tuple[str, object]]:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if is_table_line(line):
            table_lines: list[str] = []
            while index < len(lines) and is_table_line(lines[index]):
                table_lines.append(lines[index])
                index += 1
            yield "table", table_lines
            continue
        if _is_heading(line):
            yield "heading", line
            index += 1
            continue
        if re.match(r"^ANEXO\s+\d+\b", line.strip(), re.IGNORECASE):
            yield "heading", line
            index += 1
            continue

        paragraph: list[str] = []
        while index < len(lines):
            current = lines[index]
            if not current.strip() or is_table_line(current) or _is_heading(current):
                break
            paragraph.append(current.strip())
            index += 1
        if paragraph:
            yield "paragraph", paragraph


def _join_paragraph(lines: list[str]) -> str:
    if not lines:
        return ""
    if all(re.match(r"^([-+*]|\d+\.)\s+", line) for line in lines):
        return "\n".join(lines)
    return " ".join(lines)


def _word_count(text: str) -> int:
    return len(text.split())


def _split_long_paragraph(text: str, target: int = 450) -> list[str]:
    if _word_count(text) <= target * 1.35:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9])", text)
    parts: list[str] = []
    buffer: list[str] = []
    count = 0
    for sentence in sentences:
        size = _word_count(sentence)
        if buffer and count + size > target:
            parts.append(" ".join(buffer).strip())
            buffer = []
            count = 0
        buffer.append(sentence)
        count += size
    if buffer:
        parts.append(" ".join(buffer).strip())
    return [part for part in parts if part]


def _narrative_chunks(
    blocks: Iterable[str],
    *,
    section: str,
    target: int = 460,
    overlap: int = 60,
) -> list[str]:
    chunks: list[str] = []
    buffer: list[str] = []
    count = 0
    carry = ""

    def flush() -> None:
        nonlocal buffer, count, carry
        if not buffer:
            return
        body = " ".join(buffer).strip()
        if body:
            prefix = f"{section}\n\n" if section else ""
            chunks.append(f"{prefix}{body}".strip())
        sentences = re.split(r"(?<=[.!?])\s+", body)
        carry = ""
        if sentences:
            candidate = sentences[-1].strip()
            if _word_count(candidate) <= overlap:
                carry = candidate
        buffer = [carry] if carry else []
        count = _word_count(carry)

    for block in blocks:
        for part in _split_long_paragraph(block, target=target):
            size = _word_count(part)
            if buffer and count + size > target * 1.3:
                flush()
            buffer.append(part)
            count += size
            if count >= target:
                flush()

    if buffer:
        body = " ".join(buffer).strip()
        if body:
            prefix = f"{section}\n\n" if section else ""
            chunks.append(f"{prefix}{body}".strip())
    return [chunk for chunk in chunks if _word_count(chunk) >= 8]


def _table_row_text(header: list[str] | None, cells: list[str]) -> str:
    if header and len(header) == len(cells):
        pairs = [
            f"{head.strip()}: {cell.strip()}"
            for head, cell in zip(header, cells, strict=True)
            if head.strip() or cell.strip()
        ]
        if pairs:
            return " | ".join(pairs)
    return " | ".join(cell.strip() for cell in cells if cell.strip())


def _table_structure_flags(rows: list[list[str]]) -> list[str]:
    flags: list[str] = []
    if any(len(cell) > 600 for row in rows for cell in row):
        flags.append("tabla con celdas muy largas")
    duplicated = 0
    for row in rows:
        values = [cell.strip() for cell in row if cell.strip()]
        if len(values) > 1 and len(values) != len(set(values)):
            duplicated += 1
    if rows and duplicated / len(rows) >= 0.3:
        flags.append("tabla con columnas duplicadas")
    return flags


def _table_chunks(
    rows: list[list[str]],
    *,
    section: str,
    page: int,
    pdf_page: int,
    table_index: int,
    spec: DocumentSpec,
) -> list[dict]:
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return []

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    table_id = f"{spec.doc_id}-p{page}-t{table_index}"
    table_flags = _table_structure_flags(rows)
    vaccine_context = f"{section} {' '.join(cell for row in rows for cell in row)}"
    table_vaccine = detect_vaccine(vaccine_context)

    def metadata(tipo: str, row_context: str = "") -> dict:
        vaccine = detect_vaccine(f"{section} {row_context}") if row_context else table_vaccine
        item = {
            "doc_id": spec.doc_id,
            "documento": DOC_TITLE,
            "parte": spec.part,
            "pagina": page,
            "pagina_pdf": pdf_page,
            "seccion": section,
            "vacuna": vaccine,
            "tipo": tipo,
            "tabla": table_id,
        }
        if table_flags and tipo != "ficha_campo":
            item["revisar"] = True
            item["notas"] = "; ".join(table_flags)
        return item

    chunks: list[dict] = []

    # Las fichas de vacuna son tablas de dos columnas con etiquetas conocidas.
    known_fields = sum(
        1 for row in rows if normalize_field_name(row[0]) in KNOWN_FIELDS and row[0].strip()
    )
    if width == 2 and known_fields >= 2:
        for row_index, (raw_key, value) in enumerate(rows):
            key = normalize_field_name(raw_key)
            value = value.strip()
            if not value:
                continue
            text = f"{section} — {key}: {value}" if section else f"{key}: {value}"
            chunks.append(
                {
                    "texto": text,
                    "tipo": "ficha_campo",
                    "metadata": metadata("ficha_campo", f"{key} {value}"),
                    "_row": row_index,
                }
            )
        return chunks

    header = rows[0] if looks_like_header(rows[0]) else None
    data_rows = rows[1:] if header is not None else rows
    table_words = _word_count(" ".join(" ".join(row) for row in rows))
    if len(data_rows) <= 12 and table_words <= 600:
        body = "\n".join("| " + " | ".join(cell.strip() for cell in row) + " |" for row in rows)
        prefix = f"{section}\n\n" if section else ""
        chunks.append(
            {
                "texto": f"{prefix}{body}".strip(),
                "tipo": "tabla_completa",
                "metadata": metadata("tabla_completa"),
                "_row": 0,
            }
        )
        return chunks

    for row_index, row in enumerate(data_rows):
        row_text = _table_row_text(header, row)
        if not row_text:
            continue
        prefix = f"{section} — " if section else ""
        chunks.append(
            {
                "texto": f"{prefix}{row_text}".strip(),
                "tipo": "tabla_fila",
                "metadata": metadata("tabla_fila", row_text),
                "_row": row_index,
            }
        )
    return chunks


def _make_id(spec: DocumentSpec, page: int, tipo: str, ordinal: int, text: str) -> str:
    digest = hashlib.sha1(
        f"{spec.doc_id}|{spec.part}|{page}|{tipo}|{ordinal}|{text[:160]}".encode()
    ).hexdigest()[:16]
    return f"{spec.doc_id}-p{page}-{tipo}-{digest}"


def _chunk_page(
    page_text: str,
    *,
    spec: DocumentSpec,
    pdf_page: int,
    section: str,
) -> tuple[list[dict], str]:
    page = spec.page_offset + pdf_page
    narrative: list[str] = []
    chunks: list[dict] = []
    table_index = 0

    def flush_narrative() -> None:
        nonlocal narrative
        if not narrative:
            return
        for text in _narrative_chunks(narrative, section=section):
            chunks.append(
                {
                    "texto": text,
                    "tipo": "texto",
                    "metadata": {
                        "doc_id": spec.doc_id,
                        "documento": DOC_TITLE,
                        "parte": spec.part,
                        "pagina": page,
                        "pagina_pdf": pdf_page,
                        "seccion": section,
                        "vacuna": detect_vaccine(text),
                        "tipo": "texto",
                        "tabla": None,
                    },
                    "_row": 0,
                }
            )
        narrative = []

    for kind, payload in _iter_blocks(page_text):
        if kind == "heading":
            flush_narrative()
            section = _update_section(section, str(payload))
        elif kind == "paragraph":
            paragraph = _join_paragraph(payload)  # type: ignore[arg-type]
            if paragraph:
                if not section:
                    # Texto suelto antes del primer título: normalmente es
                    # cola de una tabla o ruido de OCR.
                    continue
                words = paragraph.split()
                uppercase = sum(1 for word in words if word.isupper() and len(word) > 2)
                if (
                    re.fullmatch(r"ANEXO\s+\d+", section, re.IGNORECASE)
                    and len(words) <= 20
                    and uppercase / max(len(words), 1) >= 0.5
                ):
                    section = f"{section} — {paragraph}"
                else:
                    narrative.append(paragraph)
        elif kind == "table":
            flush_narrative()
            rows = parse_table(payload)  # type: ignore[arg-type]
            if rows:
                table_index += 1
                chunks.extend(
                    _table_chunks(
                        rows,
                        section=section,
                        page=page,
                        pdf_page=pdf_page,
                        table_index=table_index,
                        spec=spec,
                    )
                )

    flush_narrative()
    return chunks, section


def _override_path(settings: Settings, spec: DocumentSpec, page: int) -> Path | None:
    """Acepta varios nombres para que el override sea fácil de escribir."""

    candidates = (
        settings.overrides_dir / f"{spec.stem}-p{page}.md",
        settings.overrides_dir / f"nts-246-parte-{spec.part}-p{page}.md",
        settings.overrides_dir / f"parte-{spec.part}-p{page}.md",
        settings.overrides_dir / f"p{page}.md",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_chunks(settings: Settings, specs: Iterable[DocumentSpec]) -> list[dict]:
    settings.ensure_dirs()
    all_chunks: list[dict] = []

    for spec in specs:
        pages_path = settings.processed_dir / f"{spec.stem}.pages.json"
        if not pages_path.exists():
            raise FileNotFoundError(
                f"Falta {pages_path}. Ejecuta primero la extracción con Docling."
            )
        raw = json.loads(pages_path.read_text(encoding="utf-8"))
        raw_pages: list[str] = raw["pages"]
        repeated = detect_repeated_edge_lines(raw_pages)
        cleaned_pages = []
        for pdf_page, raw_page in enumerate(raw_pages, start=1):
            printed_page = spec.page_offset + pdf_page
            override = _override_path(settings, spec, printed_page)
            if override is not None:
                print(f"[chunks] override aplicado: {override}")
                cleaned_pages.append(override.read_text(encoding="utf-8").strip())
            else:
                cleaned_pages.append(clean_page_markdown(raw_page, repeated))

        debug_parts: list[str] = []
        section = ""
        doc_chunks: list[dict] = []
        for pdf_page, page_text in enumerate(cleaned_pages, start=1):
            printed_page = spec.page_offset + pdf_page
            debug_parts.append(f"<!-- pagina: {printed_page} -->\n\n{page_text}")
            if printed_page in SKIP_PRINTED_PAGES:
                # Se procesa solo para actualizar la sección vigente, pero no
                # se generan chunks de formularios en blanco.
                _, section = _chunk_page(
                    page_text,
                    spec=spec,
                    pdf_page=pdf_page,
                    section=section,
                )
                debug_parts.append("<!-- página omitida: formulario en blanco -->")
                continue
            chunks, section = _chunk_page(
                page_text,
                spec=spec,
                pdf_page=pdf_page,
                section=section,
            )
            doc_chunks.extend(chunks)

        for chunk in doc_chunks:
            normalized, flags = normalize_clinical_text(chunk["texto"])
            chunk["texto"] = normalized
            existing = chunk["metadata"].get("notas") or ""
            all_flags = [item.strip() for item in existing.split(";") if item.strip()]
            all_flags.extend(flags)
            all_flags = list(dict.fromkeys(all_flags))
            chunk["metadata"]["revisar"] = bool(all_flags)
            if all_flags:
                chunk["metadata"]["notas"] = "; ".join(all_flags)

        clean_path = settings.processed_dir / f"{spec.stem}.clean.md"
        clean_path.write_text("\n\n".join(debug_parts).strip() + "\n", encoding="utf-8")

        counters: dict[tuple[str, int], int] = {}
        for chunk in doc_chunks:
            tipo = chunk["tipo"]
            page = chunk["metadata"]["pagina"]
            counters[(tipo, page)] = counters.get((tipo, page), 0) + 1
            chunk["id"] = _make_id(
                spec, page, tipo, counters[(tipo, page)], chunk["texto"]
            )
        all_chunks.extend(doc_chunks)

    with settings.chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in all_chunks:
            payload = {
                "id": chunk["id"],
                "texto": chunk["texto"],
                **chunk["metadata"],
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    flagged = [chunk for chunk in all_chunks if chunk["metadata"].get("revisar")]
    revision_path = settings.processed_dir / "revision.md"
    lines = [
        "# Valores marcados para revisión",
        "",
        "| Página | Tipo | Sección | Notas | Texto |",
        "|--------|------|---------|-------|-------|",
    ]
    for chunk in flagged:
        metadata = chunk["metadata"]
        section = str(metadata.get("seccion") or "").replace("|", "/")
        notes = str(metadata.get("notas") or "").replace("|", "/")
        text = " ".join(chunk["texto"].split())[:180].replace("|", "/")
        lines.append(
            f"| {metadata.get('pagina')} | {chunk['tipo']} | {section} | {notes} | {text} |"
        )
    revision_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return all_chunks
