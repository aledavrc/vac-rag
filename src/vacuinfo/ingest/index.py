from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from typing import Any

import chromadb

from vacuinfo.config import DOC_TITLE, Settings
from vacuinfo.rag.embeddings import Embedder

RESERVED_KEYS = {"id", "texto"}


def load_chunks(path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def _metadata(chunk: dict[str, Any]) -> dict[str, str | int | float | bool]:
    metadata: dict[str, str | int | float | bool] = {}
    for key, value in chunk.items():
        if key in RESERVED_KEYS or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
    return metadata


def _collection(settings: Settings, *, reset: bool = False):
    if reset:
        shutil.rmtree(settings.chroma_dir, ignore_errors=True)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    if reset:
        try:
            client.delete_collection(settings.chroma_collection)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,
    )


def build_index(settings: Settings, *, reset: bool = True) -> int:
    settings.ensure_dirs()
    chunks = load_chunks(settings.chunks_path)
    if not chunks:
        raise ValueError(f"No hay chunks en {settings.chunks_path}")

    collection = _collection(settings, reset=reset)
    embedder = Embedder(settings)

    batch_size = 128
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [chunk["texto"] for chunk in batch]
        embeddings = embedder.embed_documents(texts)
        collection.add(
            ids=[chunk["id"] for chunk in batch],
            documents=texts,
            embeddings=embeddings,
            metadatas=[_metadata(chunk) for chunk in batch],
        )
        print(f"[index] {min(start + batch_size, len(chunks))}/{len(chunks)}")

    manifest = {
        "documento": DOC_TITLE,
        "generado_en": datetime.now(UTC).isoformat(),
        "chunks": len(chunks),
        "embedding_model": settings.embedding_model,
        "coleccion": settings.chroma_collection,
        "chunking_version": 1,
    }
    settings.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[index] listo: {len(chunks)} chunks en {settings.chroma_dir}")
    return len(chunks)
