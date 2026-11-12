from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Filtros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vacuna: str | None = None
    seccion: str | None = None
    pagina: int | None = Field(default=None, ge=1)


class ConsultaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pregunta: str = Field(min_length=3, max_length=1000)
    k: int = Field(default=6, ge=1, le=12)
    filtros: Filtros | None = None


class BusquedaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consulta: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=6, ge=1, le=12)
    filtros: Filtros | None = None


class Fuente(BaseModel):
    chunk_id: str
    documento: str
    pagina: int
    pagina_pdf: int | None = None
    seccion: str
    vacuna: str | None = None
    tipo: str
    fragmento: str
    score: float
    revisar: bool = False
    notas: str | None = None


class ConsultaResponse(BaseModel):
    respuesta: str
    fuentes: list[Fuente]
    modo: Literal["llm", "extractivo"]
    formato: Literal["markdown"] = "markdown"
    tiempo_ms: int


class BusquedaResponse(BaseModel):
    consulta: str
    resultados: list[Fuente]
    formato: Literal["markdown"] = "markdown"
    tiempo_ms: int


class SaludResponse(BaseModel):
    estado: Literal["ok", "degradado"]
    indice_listo: bool
    chunks: int
    chunks_revisar: int = 0
    coleccion: str
    embedding_model: str
    llm_configurado: bool
    version: str
