from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import chromadb
from rank_bm25 import BM25Okapi

from vacuinfo.config import Settings
from vacuinfo.ingest.chunk import detect_vaccine
from vacuinfo.ingest.clean import normalize_for_match
from vacuinfo.rag.embeddings import Embedder

STOPWORDS = {
    "a",
    "al",
    "como",
    "con",
    "cual",
    "cuando",
    "de",
    "del",
    "el",
    "en",
    "es",
    "esta",
    "este",
    "la",
    "las",
    "lo",
    "los",
    "mas",
    "para",
    "por",
    "que",
    "se",
    "sin",
    "su",
    "sus",
    "un",
    "una",
    "y",
}


@dataclass
class RetrievedChunk:
    id: str
    text: str
    metadata: dict[str, Any]
    score: float = 0.0
    rrf: float = 0.0
    origenes: set[str] = field(default_factory=set)

    @property
    def pagina(self) -> int:
        return int(self.metadata.get("pagina", 0))

    @property
    def seccion(self) -> str:
        return str(self.metadata.get("seccion", ""))

    @property
    def vacuna(self) -> str | None:
        value = self.metadata.get("vacuna")
        return str(value) if value else None

    @property
    def tipo(self) -> str:
        return str(self.metadata.get("tipo", "texto"))


def _tokenize(text: str) -> list[str]:
    return [token for token in normalize_for_match(text).split() if token not in STOPWORDS]


def _where(filtros: Any) -> dict | None:
    if filtros is None:
        return None
    conditions: list[dict] = []
    if getattr(filtros, "vacuna", None):
        vaccine = detect_vaccine(filtros.vacuna) or filtros.vacuna
        conditions.append({"vacuna": {"$eq": vaccine}})
    if getattr(filtros, "seccion", None):
        conditions.append({"seccion": {"$eq": filtros.seccion}})
    if getattr(filtros, "pagina", None):
        conditions.append({"pagina": {"$eq": filtros.pagina}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class Retriever:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        self.collection = client.get_collection(settings.chroma_collection)
        self.embedder = Embedder(settings)

        self.chunks: list[dict[str, Any]] = []
        if settings.chunks_path.exists():
            from vacuinfo.ingest.index import load_chunks

            self.chunks = load_chunks(settings.chunks_path)
        else:
            data = self.collection.get(include=["documents", "metadatas"])
            for chunk_id, text, metadata in zip(
                data["ids"], data["documents"], data["metadatas"], strict=False
            ):
                self.chunks.append({"id": chunk_id, "texto": text, **(metadata or {})})

        self.by_id = {chunk["id"]: chunk for chunk in self.chunks}
        self.bm25 = None
        if self.chunks:
            corpus = [_tokenize(chunk.get("texto", "")) for chunk in self.chunks]
            self.bm25 = BM25Okapi(corpus)

    def search(
        self, query: str, *, k: int | None = None, filtros: Any = None
    ) -> list[RetrievedChunk]:
        k = k or self.settings.top_k
        where = _where(filtros)
        query_embedding = self.embedder.embed_query(query)
        query_tokens = set(_tokenize(query))

        candidates: dict[str, RetrievedChunk] = {}
        vector_ranked: list[str] = []
        bm25_ranked: list[str] = []

        # 1. Búsqueda vectorial
        vector = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=self.settings.vector_k,
            where=where,
            include=["documents", "metadatas"],
        )
        if vector["ids"]:
            for chunk_id, text, metadata in zip(
                vector["ids"][0],
                vector["documents"][0],
                vector["metadatas"][0],
                strict=False,
            ):
                vector_ranked.append(chunk_id)
                candidates[chunk_id] = RetrievedChunk(
                    id=chunk_id,
                    text=text or "",
                    metadata=metadata or {},
                    origenes={"vector"},
                )

        # 2. Búsqueda léxica
        if self.bm25 is not None:
            scores = self.bm25.get_scores(_tokenize(query))
            order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            for index in order:
                score = float(scores[index])
                if score <= 0:
                    break
                chunk = self.chunks[index]
                if not self._matches(chunk, filtros):
                    continue
                chunk_id = chunk["id"]
                bm25_ranked.append(chunk_id)
                if chunk_id not in candidates:
                    candidates[chunk_id] = RetrievedChunk(
                        id=chunk_id,
                        text=chunk.get("texto", ""),
                        metadata=chunk,
                        origenes={"bm25"},
                    )
                else:
                    candidates[chunk_id].origenes.add("bm25")
                if len(bm25_ranked) >= self.settings.bm25_k:
                    break

        # 3. Reciprocal Rank Fusion + pequeño refuerzo por coincidencia de sección.
        for rank, chunk_id in enumerate(vector_ranked, start=1):
            if chunk_id in candidates:
                candidates[chunk_id].rrf += 1.0 / (60 + rank)
        for rank, chunk_id in enumerate(bm25_ranked, start=1):
            if chunk_id in candidates:
                candidates[chunk_id].rrf += 1.0 / (60 + rank)
        query_vaccine = detect_vaccine(query)
        dose_field_boost = "dosis" in query_tokens and not (
            {"cuantas", "cuantos", "numero"} & query_tokens
        )
        for item in candidates.values():
            if len(query_tokens) <= 3:
                section_tokens = set(_tokenize(item.seccion))
                overlap = len(query_tokens & section_tokens)
                if overlap:
                    item.rrf += min(0.06, 0.02 * overlap)
            if query_vaccine and item.vacuna == query_vaccine:
                item.rrf += 0.02
            if dose_field_boost and "DOSIS (CANTIDAD)" in item.text.upper():
                item.rrf += 0.03
            text_tokens = set(_tokenize(item.text))
            lexical_overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            item.rrf += 0.04 * lexical_overlap

        ranked = sorted(candidates.values(), key=lambda item: item.rrf, reverse=True)[:k]
        top_rrf = ranked[0].rrf if ranked else 1.0
        for item in ranked:
            item.score = round(item.rrf / top_rrf, 4) if top_rrf else 0.0
        return ranked

    @staticmethod
    def _matches(chunk: dict[str, Any], filtros: Any) -> bool:
        if filtros is None:
            return True
        if getattr(filtros, "vacuna", None) and chunk.get("vacuna") != (
            detect_vaccine(filtros.vacuna) or filtros.vacuna
        ):
            return False
        if getattr(filtros, "seccion", None) and chunk.get("seccion") != filtros.seccion:
            return False
        if getattr(filtros, "pagina", None) and chunk.get("pagina") != filtros.pagina:
            return False
        return True

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def revisar_count(self) -> int:
        return sum(1 for chunk in self.chunks if chunk.get("revisar"))

    def suggested_vaccine(self, query: str) -> str | None:
        return detect_vaccine(query)
