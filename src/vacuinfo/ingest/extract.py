from __future__ import annotations

import json
import os
from pathlib import Path

from vacuinfo.config import DocumentSpec, Settings

# Páginas escaneadas con el contenido girado 90° dentro de la página.
# Son las tablas apaisadas de los anexos de la parte 2. Se corrigen girando la
# página del PDF (sin inyectar texto): Docling hace el OCR después.
ROTATE_PAGES: dict[int, tuple[int, ...]] = {
    2: (4, 5, 6, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33),
}

_TESSERACT_LANG = {"es": "spa", "en": "eng"}


def _ocr_options(settings: Settings):
    """Opciones de OCR nativas de Docling (sin OCRmyPDF).

    En Docling 2.149 `force_full_page_ocr` se reemplazó por `OcrMode.FULL_PAGE`.
    RapidOCR se ejecuta con ONNX Runtime y es el motor por defecto porque
    conserva mejor dosis y temperaturas que el OCR de página completa de
    Tesseract; `tesseract_cli` queda como alternativa sin dependencias Python.
    """

    from docling.datamodel.pipeline_options import (
        OcrMode,
        RapidOcrOptions,
        TesseractCliOcrOptions,
    )

    mode = OcrMode(settings.ocr_mode)
    if settings.ocr_engine == "tesseract_cli":
        # `tesseract --list-langs` de Docling no recibe `--tessdata-dir`; el
        # binario lee el idioma desde TESSDATA_PREFIX al inicializar el modelo.
        os.environ["TESSDATA_PREFIX"] = str(settings.tessdata_dir.resolve())
        languages = [_TESSERACT_LANG.get(lang, lang) for lang in settings.ocr_lang]
        return TesseractCliOcrOptions(
            lang=languages,
            scale=settings.ocr_scale,
            mode=mode,
            path=str(settings.tessdata_dir),
            psm=settings.ocr_psm,
        )
    return RapidOcrOptions(
        lang=settings.ocr_lang,
        scale=settings.ocr_scale,
        mode=mode,
        backend="onnxruntime",
        model_size=settings.ocr_model_size,
    )


def pipeline_options(settings: Settings):
    """Opciones del pipeline PDF de Docling (layout + tablas + OCR)."""

    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        generate_page_images=False,
        images_scale=settings.images_scale,
        ocr_options=_ocr_options(settings),
    )
    options.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE,
    )
    return options


def _converter(settings: Settings):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options(settings))
        }
    )


def _rotated_source(spec: DocumentSpec, settings: Settings) -> Path:
    """Gira las páginas apaisadas sin añadir texto ni ejecutar OCR."""

    pages = ROTATE_PAGES.get(spec.part)
    if not pages:
        return spec.pdf

    from pypdf import PdfReader, PdfWriter

    output = settings.derived_dir / f"{spec.stem}-rotada.pdf"
    if output.exists() and output.stat().st_mtime >= spec.pdf.stat().st_mtime:
        return output

    reader = PdfReader(str(spec.pdf))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index in pages:
            page.rotate(90)
        writer.add_page(page)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    print(f"[extract] orientación corregida en páginas {pages} -> {output}")
    return output


def _content_labels():
    """Etiquetas que aportan contenido; excluye encabezados, pies e imágenes."""

    from docling_core.types.doc import DocItemLabel

    return {label for label in DocItemLabel} - {
        DocItemLabel.PAGE_HEADER,
        DocItemLabel.PAGE_FOOTER,
        DocItemLabel.PICTURE,
    }


def _page_markdown(document, page_no: int, labels) -> str:
    return document.export_to_markdown(page_no=page_no, labels=labels)


def _page_labels(document, page_no: int) -> list[str]:
    labels: list[str] = []
    for item, _level in document.iterate_items(page_no=page_no):
        label = getattr(item, "label", None)
        if label is not None:
            labels.append(str(getattr(label, "value", label)))
    return labels


def extract_documents(
    settings: Settings,
    specs: tuple[DocumentSpec, ...],
    *,
    force: bool = False,
) -> None:
    """Extrae Markdown por página con OCR nativo de Docling.

    Guarda `data/processed/<stem>.pages.json` con la clave `pages` (contrato que
    consume el chunker) y metadatos de trazabilidad del OCR y del layout.
    """

    settings.ensure_dirs()
    converter = _converter(settings)
    labels = _content_labels()

    for spec in specs:
        pages_path = settings.processed_dir / f"{spec.stem}.pages.json"
        if pages_path.exists() and not force:
            print(f"[extract] existe, se reutiliza: {pages_path}")
            continue

        source = _rotated_source(spec, settings)
        print(
            f"[extract] Docling OCR={settings.ocr_engine} "
            f"mode={settings.ocr_mode} scale={settings.images_scale}: {source}"
        )
        result = converter.convert(source)
        document = result.document
        page_count = len(document.pages)
        pages: list[str] = []
        page_labels: list[dict] = []
        empty_pages: list[int] = []

        for page_no in range(1, page_count + 1):
            markdown = _page_markdown(document, page_no, labels)
            pages.append(markdown)
            page_labels.append(
                {"pagina_pdf": page_no, "labels": _page_labels(document, page_no)}
            )
            if not markdown.strip():
                empty_pages.append(page_no)

        payload = {
            "source_pdf": str(spec.pdf),
            "derived_pdf": str(source),
            "part": spec.part,
            "page_offset": spec.page_offset,
            "pages": pages,
            "page_labels": page_labels,
            "tables_detected": len(document.tables),
            "texts_detected": len(document.texts),
            "empty_pages": empty_pages,
            "ocr": {
                "engine": settings.ocr_engine,
                "lang": settings.ocr_lang,
                "mode": settings.ocr_mode,
                "scale": settings.ocr_scale,
                "images_scale": settings.images_scale,
            },
        }
        pages_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[extract] {pages_path}: {page_count} páginas, "
            f"{len(document.tables)} tablas, {len(empty_pages)} vacías"
        )
