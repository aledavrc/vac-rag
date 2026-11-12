from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DOC_ID = "nts-246-2026"
DOC_TITLE = "NTS N° 246-MINSA/DGIESP-2026"


class Settings(BaseSettings):
    """Configuración tomada de variables VACUINFO_* o de un archivo .env."""

    model_config = SettingsConfigDict(
        env_prefix="VACUINFO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pdf_dir: Path = Path("pdf")
    data_dir: Path = Path("data")
    models_dir: Path = Path("models")

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chroma_collection: str = "normativa_vacunacion"

    top_k: int = 6
    vector_k: int = 10
    bm25_k: int = 10

    llm_base_url: str | None = None
    llm_model: str = "qwen2.5:7b"
    llm_api_key: str = "ollama"
    llm_timeout: float = 60.0

    ocr_jobs: int = 4

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def ocr_dir(self) -> Path:
        return self.data_dir / "ocr"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def overrides_dir(self) -> Path:
        return self.data_dir / "overrides"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "index" / "chroma"

    @property
    def chunks_path(self) -> Path:
        return self.data_dir / "chunks.jsonl"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "manifest.json"

    @property
    def fastembed_cache(self) -> Path:
        return self.models_dir / "fastembed"

    @property
    def tessdata_dir(self) -> Path:
        return self.models_dir / "tessdata"

    def ensure_dirs(self) -> None:
        for path in (
            self.ocr_dir,
            self.processed_dir,
            self.overrides_dir,
            self.chroma_dir,
            self.fastembed_cache,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class DocumentSpec:
    doc_id: str
    titulo: str
    pdf: Path
    part: int
    page_offset: int
    pages: int

    @property
    def stem(self) -> str:
        return self.pdf.stem

    @property
    def ocr_path(self) -> Path:
        return Path("data/ocr") / f"{self.stem}.pdf"

    def ocr_path_in(self, settings: Settings) -> Path:
        return settings.ocr_dir / f"nts-246-parte-{self.part}.pdf"

    @property
    def printed_first_page(self) -> int:
        return self.page_offset + 1


def _pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


def _part_number(path: Path, fallback: int) -> int:
    match = re.search(r"parte[-_ ]?(\d+)", path.stem, re.IGNORECASE)
    return int(match.group(1)) if match else fallback


@lru_cache(maxsize=4)
def discover_documents(pdf_dir: str) -> tuple[DocumentSpec, ...]:
    """Descubre los PDF y calcula la numeración impresa acumulada.

    La parte 1 empieza en la página 1; la parte 2 continúa donde terminó la
    anterior. Así las citas usan la página impresa del documento completo.
    """

    root = Path(pdf_dir)
    pdfs = sorted(root.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No se encontraron PDF en {root.resolve()}")

    specs: list[DocumentSpec] = []
    offset = 0
    for index, pdf in enumerate(pdfs, start=1):
        pages = _pdf_page_count(pdf)
        part = _part_number(pdf, index)
        specs.append(
            DocumentSpec(
                doc_id=DOC_ID,
                titulo=DOC_TITLE,
                pdf=pdf,
                part=part,
                page_offset=offset,
                pages=pages,
            )
        )
        offset += pages
    return tuple(specs)


def get_settings() -> Settings:
    return Settings()
