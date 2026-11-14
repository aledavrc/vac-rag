from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

from rapidfuzz import fuzz, process

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
_KNOWN_NORMALIZED = tuple(_KNOWN_BY_NORMALIZED)
_OCR_FIELD_FIXES = {
    "ion": "INDICACIÓN",
    "e": "CONSERVACIÓN DE LA VACUNA",
    "incas a": "JERINGAS A UTILIZAR",
    "post res": "POSIBLES EFECTOS POST-VACUNALES",
    "conservacion de": "CONSERVACIÓN DE LA VACUNA",
    "administracion via y sitio de": "VÍA Y SITIO DE ADMINISTRACIÓN",
    "simultaneo otras uso con vacunas": "USO SIMULTÁNEO CON OTRAS VACUNAS",
    "esquema": "ESQUEMA DE VACUNACIÓN",
    "tipo inmunizacion": "TIPO DE VACUNA",
}

# Número de sección colado en la clave (ej. "6.1.1.6. VACUNA CONTRA …").
_SECTION_PREFIX = re.compile(r"^\d+(?:\.\d+)+\s*\.?\s*")
# Encabezado de sección sin "##" (ej. "6.1.1.10. VACUNA ANTINEUMOCÓCICA (*)").
_SECTION_HEADING = re.compile(r"^\d+(?:\.\d+)+\s*\.\s+[A-ZÁÉÍÓÚÑ]")

# Cutoff del matcher fuzzy: por debajo la clave queda sin resolver y se marca.
_FIELD_FUZZY_CUTOFF = 80.0


def _field_similarity(query: str, candidate: str, **_kwargs: object) -> float:
    """Combina token_sort_ratio (reordenamiento/truncamiento) con ratio
    (palabras partidas) tomando el máximo; el cutoff descarta falsos positivos."""

    return max(fuzz.token_sort_ratio(query, candidate), fuzz.ratio(query, candidate))


# Formularios y registros en blanco de los anexos: no aportan respuestas y
# generan mucho ruido de OCR.
SKIP_PRINTED_PAGES = frozenset({101, 102, 103, *range(121, 131), *range(131, 140)})


def normalize_field_name(key: str) -> str:
    """Corrige etiquetas de ficha mal OCR sin tocar el contenido clínico."""

    cleaned = re.sub(r"[|\s]+", " ", key).strip(" []").strip()
    if not cleaned:
        return "Continuación"
    stripped = _SECTION_PREFIX.sub("", cleaned).strip()
    normalized = normalize_for_match(stripped)
    if normalized in _OCR_FIELD_FIXES:
        return _OCR_FIELD_FIXES[normalized]
    if normalized in _KNOWN_BY_NORMALIZED:
        return _KNOWN_BY_NORMALIZED[normalized]
    # La clave es la cola de un campo canónico (etiqueta truncada).
    for candidate, display in _KNOWN_BY_NORMALIZED.items():
        if len(normalized) >= 5 and candidate.endswith(normalized):
            return display
    if stripped != cleaned:
        # El encabezado de la sección se coló delante de la clave: recupera el
        # campo conocido que queda como sufijo (el más largo desempata).
        suffix: tuple[str, str] | None = None
        for candidate, display in _KNOWN_BY_NORMALIZED.items():
            if normalized.endswith(candidate) and len(normalized) > len(candidate):
                if suffix is None or len(candidate) > len(suffix[0]):
                    suffix = (candidate, display)
        if suffix is not None:
            return suffix[1]
    match = process.extractOne(
        normalized,
        _KNOWN_NORMALIZED,
        scorer=_field_similarity,
        score_cutoff=_FIELD_FUZZY_CUTOFF,
    )
    return _KNOWN_BY_NORMALIZED[match[0]] if match else cleaned


def _split_fused_key(key: str) -> tuple[str, str] | None:
    """Detecta una clave que fusiona dos campos canónicos consecutivos.

    Solo se parte si la clave normalizada es exactamente la concatenación de
    dos campos consecutivos de `KNOWN_FIELDS` (separados por espacios o signos).
    Esto descarta claves sueltas como "CONTRAINDICACIÓN", que contiene
    "INDICACIÓN" como subcadena pero no es una fusión.
    """

    normalized = normalize_for_match(key)
    for i in range(len(KNOWN_FIELDS) - 1):
        first = normalize_for_match(KNOWN_FIELDS[i])
        second = normalize_for_match(KNOWN_FIELDS[i + 1])
        if re.fullmatch(re.escape(first) + r"[\W_]+" + re.escape(second), normalized):
            return KNOWN_FIELDS[i], KNOWN_FIELDS[i + 1]
    return None


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
        if _SECTION_HEADING.match(line.strip()):
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
            if (
                not current.strip()
                or is_table_line(current)
                or _is_heading(current)
                or _SECTION_HEADING.match(current.strip())
            ):
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


def _is_ficha(rows: list[list[str]]) -> bool:
    """Ficha key-value si la 1ª columna no vacía es mayormente KNOWN_FIELDS."""

    labels = [row[0].strip() for row in rows if row[0].strip()]
    if len(labels) < 2:
        return False
    known = sum(1 for label in labels if normalize_field_name(label) in KNOWN_FIELDS)
    return known >= 2 and known >= 0.5 * len(labels)


def _value_columns(rows: list[list[str]]) -> list[int]:
    """Columnas de valor (>= 1), descartando las que están casi vacías."""

    width = len(rows[0])
    total = len(rows)
    kept = [
        j
        for j in range(1, width)
        if sum(1 for row in rows if row[j].strip()) >= 0.5 * total
    ]
    return kept or list(range(1, width))


def _join_values(cells: list[str]) -> str:
    """Une celdas de valor no vacías, sin duplicados exactos."""

    seen: list[str] = []
    for cell in cells:
        value = cell.strip()
        if value and value not in seen:
            seen.append(value)
    return " | ".join(seen)


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

    # Las fichas de vacuna son tablas key-value cuya 1ª columna es mayormente
    # etiquetas conocidas; admiten 2 o más columnas (variantes/duplicados).
    if _is_ficha(rows):
        value_cols = _value_columns(rows)

        def make_chunk(key: str, value: str, row_index: int, meta: dict) -> dict:
            text = f"{section} — {key}: {value}" if section else f"{key}: {value}"
            return {
                "texto": text,
                "tipo": "ficha_campo",
                "metadata": meta,
                "_row": row_index,
                "_key": key,
                "_value": value,
            }

        row_index = 0
        while row_index < len(rows):
            raw_key = rows[row_index][0]
            value = _join_values([rows[row_index][j] for j in value_cols])
            if not value:
                row_index += 1
                continue

            # Fase 5: partir una celda de clave que fusiona dos campos.
            fused = _split_fused_key(raw_key)
            if fused is not None:
                first, second = fused
                continuation = ""
                if row_index + 1 < len(rows) and not rows[row_index + 1][0].strip():
                    continuation = _join_values(
                        [rows[row_index + 1][j] for j in value_cols]
                    )
                if continuation:
                    # Partición segura: el 1er campo toma la celda actual y el
                    # 2º la fila de continuación que le sigue.
                    chunks.append(
                        make_chunk(
                            first,
                            value,
                            row_index,
                            metadata("ficha_campo", f"{first} {value}"),
                        )
                    )
                    chunks.append(
                        make_chunk(
                            second,
                            continuation,
                            row_index + 1,
                            metadata("ficha_campo", f"{second} {continuation}"),
                        )
                    )
                    row_index += 2
                    continue
                # Sin continuación: el valor no se puede repartir con seguridad;
                # se conserva íntegro en el 2º campo y se marca para revisión.
                meta = metadata("ficha_campo", f"{second} {value}")
                meta["revisar"] = True
                meta["notas"] = f"clave fusionada ({first} + {second}); valor no separable"
                chunks.append(make_chunk(second, value, row_index, meta))
                row_index += 1
                continue

            key = normalize_field_name(raw_key)
            meta = metadata("ficha_campo", f"{key} {value}")
            if key != "Continuación" and key not in KNOWN_FIELDS:
                # Clave OCR no resuelta: se conserva y se marca (no se infiere).
                meta["revisar"] = True
                meta["notas"] = "clave no canónica (OCR)"
            chunks.append(make_chunk(key, value, row_index, meta))
            row_index += 1
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


def _field_text(key: str, value: str, section: str) -> str:
    """Texto de un campo de ficha, con el mismo formato que `_table_chunks`."""

    return f"{section} — {key}: {value}" if section else f"{key}: {value}"


def _concat_value(base: str, continuation: str) -> str:
    """Concatena una continuación al valor previo con un único espacio."""

    return " ".join(part for part in (base.strip(), continuation.strip()) if part)


def _merge_ficha_continuations(chunks: list[dict]) -> list[dict]:
    """Fusiona filas de ficha con clave vacía ("Continuación") en el campo previo.

    Regla (Fase 4, alineada con ADR-002 y ADR-004):

    - Una fila de ficha con clave vacía continúa el valor del último campo de la
      misma sección; su valor se concatena al campo anterior (misma página o
      página siguiente) y el chunk huérfano desaparece.
    - Una clave "TIPO DE VACUNA" abre una ficha nueva y una tabla que no es ficha
      ("tabla_completa"/"tabla_fila", p. ej. esquemas o anexos) cierra el
      contexto. Así no se fusionan fichas distintas ni tablas de anexos.
    - Los chunks "texto" se ignoran a efectos de continuidad: entre una ficha
      partida y su continuación solo pueden colarse encabezados/pies de página
      residuales, que no deben romper la ficha.
    - Si no hay campo previo en la misma sección (continuación huérfana), el
      chunk se conserva y se marca "revisar" en vez de inferir la clave.
    """

    merged: list[dict] = []
    current: dict | None = None
    for chunk in chunks:
        tipo = chunk.get("tipo")
        if tipo != "ficha_campo":
            if tipo in ("tabla_completa", "tabla_fila"):
                current = None
            # "texto": transparente (ver docstring).
            merged.append(chunk)
            continue

        key = chunk.get("_key")
        value = chunk.get("_value", "")
        section = chunk["metadata"].get("seccion")

        if key == "TIPO DE VACUNA":
            current = {"chunk": chunk, "key": key, "value": value, "section": section}
            merged.append(chunk)
            continue

        if key == "Continuación":
            if current is not None and current["section"] == section:
                current["value"] = _concat_value(current["value"], value)
                current["chunk"]["_value"] = current["value"]
                current["chunk"]["texto"] = _field_text(
                    current["key"], current["value"], current["section"]
                )
            else:
                chunk["metadata"]["revisar"] = True
                chunk["metadata"]["notas"] = "continuación sin campo previo"
                merged.append(chunk)
            continue

        current = {"chunk": chunk, "key": key, "value": value, "section": section}
        merged.append(chunk)

    return merged


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

        doc_chunks = _merge_ficha_continuations(doc_chunks)

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
