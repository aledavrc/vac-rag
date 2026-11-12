from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from vacuinfo.config import DOC_TITLE, Settings
from vacuinfo.ingest.clean import normalize_for_match
from vacuinfo.rag.formatting import clip_markdown, format_chunk_markdown
from vacuinfo.rag.retrieve import RetrievedChunk

logger = logging.getLogger(__name__)

GENERIC_QUERY_TERMS = {
    "aplicar",
    "aplicacion",
    "aparecer",
    "asociada",
    "asociado",
    "contra",
    "cual",
    "cuales",
    "cuando",
    "cuanta",
    "cuanto",
    "debe",
    "dice",
    "dosis",
    "donde",
    "entre",
    "esquema",
    "esta",
    "hasta",
    "informacion",
    "manejo",
    "nina",
    "nino",
    "norma",
    "para",
    "persona",
    "puede",
    "que",
    "segun",
    "sobre",
    "tarda",
    "tiempo",
    "tratamiento",
    "usa",
    "uso",
    "vacuna",
    "vacunas",
}

SYSTEM_PROMPT = """Eres un asistente documental especializado en la normativa de vacunación \
del Perú.
Responde en español, de forma breve y literal, usando únicamente los fragmentos entregados.
Cada afirmación debe llevar una cita con el formato [NTS 246, p. <página>, sección <sección>].
No inventes edades, dosis, intervalos, vías, temperaturas ni contraindicaciones.
No completes información con conocimiento general.
Si una fuente está marcada para revisión, indícalo al final de la respuesta.
Si los fragmentos no contienen la respuesta, responde exactamente:
"No se encontró esa información en la normativa cargada."
Responde en Markdown. Usa listas con viñetas cuando haya varios elementos y tablas Markdown
cuando los datos sean tabulares. No devuelvas HTML.
"""


@dataclass
class AnswerResult:
    text: str
    mode: str


def _citation(chunk: RetrievedChunk) -> str:
    section = chunk.seccion or "sin sección"
    return f"[{DOC_TITLE}, p. {chunk.pagina}, sección {section}]"


def _extractive(chunks: list[RetrievedChunk]) -> AnswerResult:
    if not chunks:
        return AnswerResult(
            text="No se encontró esa información en la normativa cargada.",
            mode="extractivo",
        )
    lines = ["**Según la normativa cargada:**", ""]
    for chunk in chunks[:1]:
        if chunk.metadata.get("revisar"):
            notes = chunk.metadata.get("notas") or "valor dudoso"
            lines.append(f"> ⚠️ **Fuente marcada para revisión:** {notes}")
            lines.append("")
        lines.append(format_chunk_markdown(chunk.text))
        lines.append("")
        lines.append(f"*Fuente: {_citation(chunk)}*")
        lines.append("")
    return AnswerResult(text="\n".join(lines).strip(), mode="extractivo")


def _significant_terms(query: str) -> set[str]:
    tokens = normalize_for_match(query).split()
    return {
        token
        for token in tokens
        if len(token) >= 4 and token not in GENERIC_QUERY_TERMS
    }


def is_answerable(query: str, chunks: list[RetrievedChunk]) -> bool:
    """Evita responder cuando la pregunta introduce términos ajenos al corpus.

    Es una salvaguarda barata para el modo extractivo. Con un LLM configurado,
    el prompt también puede abstenerse, pero esta comprobación reduce respuestas
    claramente fuera de alcance.
    """

    terms = _significant_terms(query)
    if not terms:
        return True
    corpus = normalize_for_match(" ".join(chunk.text for chunk in chunks))
    return any(re.search(rf"\b{re.escape(term)}", corpus) for term in terms)


def _context(chunks: list[RetrievedChunk], max_chars: int = 16_000) -> str:
    blocks: list[str] = []
    used = 0
    for index, chunk in enumerate(chunks, start=1):
        block = (
            f"[Fuente {index}] {DOC_TITLE}, p. {chunk.pagina}, "
            f"sección {chunk.seccion or 'sin sección'}\n"
            f"{clip_markdown(chunk.text, 1200)}"
        )
        if chunk.metadata.get("revisar"):
            block += f"\n[MARCADO PARA REVISIÓN: {chunk.metadata.get('notas', 'valor dudoso')}]"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def _llm_answer(
    settings: Settings, query: str, chunks: list[RetrievedChunk]
) -> AnswerResult | None:
    if not settings.llm_base_url:
        return None
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Pregunta: {query}\n\n"
                    f"Fragmentos disponibles:\n{_context(chunks)}\n\n"
                    "Responde citando la página y la sección."
                ),
            },
        ],
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=settings.llm_timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()
        if not text:
            return None
        return AnswerResult(text=text, mode="llm")
    except Exception as exc:  # noqa: BLE001
        logger.warning("El LLM no respondió, se usa modo extractivo: %s", exc)
        return None


def generate_answer(settings: Settings, query: str, chunks: list[RetrievedChunk]) -> AnswerResult:
    if not chunks or not is_answerable(query, chunks):
        return _extractive([])
    result = _llm_answer(settings, query, chunks)
    return result if result is not None else _extractive(chunks)
