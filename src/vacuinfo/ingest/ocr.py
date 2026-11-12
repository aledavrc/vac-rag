from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from vacuinfo.config import DocumentSpec, Settings

# Páginas escaneadas con el contenido girado 90° dentro de la página.
# Son las tablas apaisadas de los anexos de la parte 2.
ROTATE_PAGES: dict[int, tuple[int, ...]] = {
    2: (4, 5, 6, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33),
}


def _source_for_ocr(spec: DocumentSpec, settings: Settings) -> Path:
    pages = ROTATE_PAGES.get(spec.part)
    if not pages:
        return spec.pdf

    from pypdf import PdfReader, PdfWriter

    output = settings.ocr_dir / f"{spec.stem}-fuente-rotada.pdf"
    reader = PdfReader(str(spec.pdf))
    writer = PdfWriter()
    for index, page in enumerate(reader.pages, start=1):
        if index in pages:
            page.rotate(90)
        writer.add_page(page)
    with output.open("wb") as handle:
        writer.write(handle)
    print(f"[ocr] orientación corregida en páginas {pages} -> {output}")
    return output


def _tessconfig(settings: Settings) -> Path:
    """Configura Tesseract con vocabulario y patrones del dominio."""

    resources = Path(__file__).resolve().parent.parent / "data"
    words = resources / "vacuinfo.user-words"
    patterns = resources / "vacuinfo.patterns"
    if not words.exists() or not patterns.exists():
        raise FileNotFoundError(f"Faltan los recursos OCR en {resources}")

    config = settings.ocr_dir / "vacuinfo.tessconfig"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        "\n".join(
            (
                f"user_words_file {words}",
                f"user_patterns_file {patterns}",
                "preserve_interword_spaces 1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return config


def run_ocr(settings: Settings, specs: tuple[DocumentSpec, ...], *, force: bool = False) -> None:
    """Genera un PDF buscable por cada PDF original usando OCRmyPDF."""

    settings.ensure_dirs()
    if not (settings.tessdata_dir / "spa.traineddata").exists():
        raise FileNotFoundError(
            f"Falta {settings.tessdata_dir}/spa.traineddata. "
            "Descarga el modelo de español antes de ejecutar el OCR."
        )

    env = os.environ.copy()
    env["TESSDATA_PREFIX"] = str(settings.tessdata_dir.resolve())
    tessconfig = _tessconfig(settings)

    for spec in specs:
        output = spec.ocr_path_in(settings)
        if output.exists() and not force:
            print(f"[ocr] existe, se reutiliza: {output}")
            continue
        output.parent.mkdir(parents=True, exist_ok=True)
        source = _source_for_ocr(spec, settings)
        command = [
            sys.executable,
            "-m",
            "ocrmypdf",
            "--language",
            "spa",
            "--oversample",
            "300",
            "--tesseract-oem",
            "1",
            "--tesseract-pagesegmode",
            "3",
            "--tesseract-config",
            str(tessconfig.resolve()),
            "--deskew",
            "--clean",
            "--optimize",
            "1",
            "--output-type",
            "pdf",
            "--jobs",
            str(settings.ocr_jobs),
            str(source),
            str(output),
        ]
        print(f"[ocr] {source} -> {output}")
        subprocess.run(command, check=True, env=env)
