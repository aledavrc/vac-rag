from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from vacuinfo import __version__
from vacuinfo.config import DOC_TITLE, get_settings
from vacuinfo.rag.answer import generate_answer
from vacuinfo.rag.formatting import clip_markdown
from vacuinfo.rag.retrieve import Retriever
from vacuinfo.schemas import (
    BusquedaRequest,
    BusquedaResponse,
    ConsultaRequest,
    ConsultaResponse,
    Fuente,
    SaludResponse,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.retriever = None
    app.state.error = None
    try:
        app.state.retriever = Retriever(settings)
    except Exception as exc:  # noqa: BLE001
        app.state.error = str(exc)
        logging.getLogger(__name__).warning("Índice no disponible: %s", exc)
    yield


app = FastAPI(
    title="VacuInfo",
    description=f"Consulta con RAG de la {DOC_TITLE}",
    version=__version__,
    lifespan=lifespan,
)


def _retriever(request: Request) -> Retriever:
    retriever = request.app.state.retriever
    if retriever is None:
        detail = request.app.state.error or "El índice no está construido."
        raise HTTPException(status_code=503, detail=f"Servicio no disponible: {detail}")
    return retriever


def _fuente(chunk) -> Fuente:
    return Fuente(
        chunk_id=chunk.id,
        documento=chunk.metadata.get("documento", DOC_TITLE),
        pagina=chunk.pagina,
        pagina_pdf=chunk.metadata.get("pagina_pdf"),
        seccion=chunk.seccion,
        vacuna=chunk.vacuna,
        tipo=chunk.tipo,
        fragmento=clip_markdown(chunk.text, 1200),
        score=chunk.score,
        revisar=bool(chunk.metadata.get("revisar", False)),
        notas=chunk.metadata.get("notas"),
    )


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "servicio": "VacuInfo",
        "documento": DOC_TITLE,
        "docs": "/docs",
        "salud": "/salud",
    }


@app.get("/salud", response_model=SaludResponse)
def salud(request: Request) -> SaludResponse:
    retriever = request.app.state.retriever
    settings = request.app.state.settings
    return SaludResponse(
        estado="ok" if retriever is not None else "degradado",
        indice_listo=retriever is not None,
        chunks=retriever.chunk_count if retriever is not None else 0,
        chunks_revisar=retriever.revisar_count if retriever is not None else 0,
        coleccion=settings.chroma_collection,
        embedding_model=settings.embedding_model,
        llm_configurado=bool(settings.llm_base_url),
        version=__version__,
    )


@app.post("/consulta", response_model=ConsultaResponse)
def consulta(request: Request, body: ConsultaRequest) -> ConsultaResponse:
    retriever = _retriever(request)
    settings = request.app.state.settings
    started = time.perf_counter()
    chunks = retriever.search(body.pregunta, k=body.k, filtros=body.filtros)
    answer = generate_answer(settings, body.pregunta, chunks)
    elapsed = int((time.perf_counter() - started) * 1000)
    return ConsultaResponse(
        respuesta=answer.text,
        fuentes=[_fuente(chunk) for chunk in chunks],
        modo=answer.mode,  # type: ignore[arg-type]
        tiempo_ms=elapsed,
    )


@app.post("/buscar", response_model=BusquedaResponse)
def buscar(request: Request, body: BusquedaRequest) -> BusquedaResponse:
    retriever = _retriever(request)
    started = time.perf_counter()
    chunks = retriever.search(body.consulta, k=body.k, filtros=body.filtros)
    elapsed = int((time.perf_counter() - started) * 1000)
    return BusquedaResponse(
        consulta=body.consulta,
        resultados=[_fuente(chunk) for chunk in chunks],
        tiempo_ms=elapsed,
    )
