from __future__ import annotations

import json

from vacuinfo.config import DocumentSpec, Settings


def _converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=False,
        do_table_structure=True,
        generate_page_images=False,
        images_scale=1.0,
    )
    options.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def extract_documents(
    settings: Settings,
    specs: tuple[DocumentSpec, ...],
    *,
    force: bool = False,
) -> None:
    """Extrae Markdown por página y lo guarda en data/processed."""

    settings.ensure_dirs()
    converter = _converter()

    for spec in specs:
        pages_path = settings.processed_dir / f"{spec.stem}.pages.json"
        if pages_path.exists() and not force:
            print(f"[extract] existe, se reutiliza: {pages_path}")
            continue

        ocr_path = spec.ocr_path_in(settings)
        if not ocr_path.exists():
            raise FileNotFoundError(f"Falta el PDF OCR: {ocr_path}")

        print(f"[extract] Docling: {ocr_path}")
        result = converter.convert(ocr_path)
        document = result.document
        page_count = len(document.pages)
        pages: list[str] = []
        empty_pages: list[int] = []

        for page_no in range(1, page_count + 1):
            markdown = document.export_to_markdown(page_no=page_no)
            pages.append(markdown)
            if not markdown.strip():
                empty_pages.append(page_no)

        payload = {
            "source_pdf": str(spec.pdf),
            "ocr_pdf": str(ocr_path),
            "part": spec.part,
            "page_offset": spec.page_offset,
            "pages": pages,
            "tables_detected": len(document.tables),
            "texts_detected": len(document.texts),
            "empty_pages": empty_pages,
        }
        pages_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[extract] {pages_path}: {page_count} páginas, "
            f"{len(document.tables)} tablas, {len(empty_pages)} vacías"
        )
