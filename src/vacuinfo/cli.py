from __future__ import annotations

import argparse
import json
from collections import Counter

from vacuinfo.config import discover_documents, get_settings
from vacuinfo.ingest.chunk import build_chunks
from vacuinfo.ingest.extract import extract_documents
from vacuinfo.ingest.index import build_index
from vacuinfo.rag.answer import generate_answer
from vacuinfo.rag.retrieve import Retriever


def _specs(settings):
    return discover_documents(str(settings.pdf_dir))


def cmd_ingestar(args: argparse.Namespace) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    specs = _specs(settings)

    if not args.solo_indice:
        if not args.sin_extraccion:
            extract_documents(settings, specs, force=args.fuerza_extraccion)
        chunks = build_chunks(settings, specs)
        counts = Counter(chunk["tipo"] for chunk in chunks)
        revisar = sum(1 for chunk in chunks if chunk["metadata"].get("revisar"))
        print(f"[chunks] {len(chunks)} en total: {dict(counts)}; para revisar: {revisar}")

    if not args.sin_indice:
        build_index(settings, reset=True)


def cmd_extraer(args: argparse.Namespace) -> None:
    settings = get_settings()
    specs = _specs(settings)
    if args.parte:
        specs = tuple(spec for spec in specs if spec.part == args.parte)
    extract_documents(settings, specs, force=args.fuerza)


def cmd_chunks(args: argparse.Namespace) -> None:
    settings = get_settings()
    chunks = build_chunks(settings, _specs(settings))
    revisar = sum(1 for chunk in chunks if chunk["metadata"].get("revisar"))
    print(f"[chunks] {len(chunks)} escritos en {settings.chunks_path}; para revisar: {revisar}")


def cmd_indexar(args: argparse.Namespace) -> None:
    settings = get_settings()
    build_index(settings, reset=not args.sin_reiniciar)


def _print_chunks(settings, question: str, k: int, *, answer: bool) -> None:
    retriever = Retriever(settings)
    chunks = retriever.search(question, k=k)
    if answer:
        result = generate_answer(settings, question, chunks)
        print(result.text)
        print(f"\n[modo: {result.mode}]")
    else:
        for index, chunk in enumerate(chunks, start=1):
            print(f"\n--- [{index}] score={chunk.score} ---")
            print(f"p. {chunk.pagina} | {chunk.seccion} | {chunk.vacuna or '-'}")
            print(" ".join(chunk.text.split())[:900])


def cmd_consultar(args: argparse.Namespace) -> None:
    settings = get_settings()
    retriever = Retriever(settings)
    chunks = retriever.search(args.pregunta, k=args.k)
    result = generate_answer(settings, args.pregunta, chunks)
    if args.json:
        print(
            json.dumps(
                {
                    "respuesta": result.text,
                    "modo": result.mode,
                    "fuentes": [
                        {
                            "pagina": chunk.pagina,
                            "seccion": chunk.seccion,
                            "tipo": chunk.tipo,
                            "score": chunk.score,
                            "fragmento": " ".join(chunk.text.split())[:500],
                        }
                        for chunk in chunks
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if args.render:
        from rich.console import Console
        from rich.markdown import Markdown

        Console().print(Markdown(result.text.replace("<br>", " · ")))
    else:
        print(result.text)
    print(f"\n[modo: {result.mode}]")
    for index, chunk in enumerate(chunks, start=1):
        print(f"[{index}] p. {chunk.pagina} | {chunk.seccion} | {chunk.tipo}")


def cmd_buscar(args: argparse.Namespace) -> None:
    _print_chunks(get_settings(), args.consulta, args.k, answer=False)


def cmd_evaluar(args: argparse.Namespace) -> None:
    from vacuinfo.ingest.clean import normalize_for_match

    settings = get_settings()
    retriever = Retriever(settings)
    rows = [
        json.loads(line)
        for line in open(args.archivo, encoding="utf-8")
        if line.strip()
    ]
    hits = 0
    evaluables = 0
    for row in rows:
        page = row.get("pagina")
        if page is None:
            continue
        evaluables += 1
        expected_section = normalize_for_match(row.get("seccion", ""))
        chunks = retriever.search(row["pregunta"], k=args.k)
        hit = any(
            chunk.pagina == page
            and (
                not expected_section
                or expected_section in normalize_for_match(chunk.seccion)
            )
            for chunk in chunks
        )
        hits += int(hit)
        estado = "OK" if hit else "FALLA"
        print(f"[{estado}] p.{page} | {row['pregunta'][:90]}")
        if not hit:
            encontrados = ", ".join(f"p.{c.pagina}" for c in chunks[:5])
            print(f"        recuperado: {encontrados}")
    if evaluables:
        print(f"\nHit@{args.k}: {hits}/{evaluables} = {hits / evaluables:.2f}")
    print(f"Preguntas fuera de alcance: {len(rows) - evaluables}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Comprueba lo mínimo para consultar y para ingestar en una máquina nueva."""

    import importlib.util
    import sys

    settings = get_settings()
    print(f"Python {sys.version.split()[0]} · {sys.executable}")
    print(f"Directorio: {settings.data_dir.resolve().parent}")

    def check(label: str, condition: bool, hint: str) -> None:
        print(f"[{'OK   ' if condition else 'FALTA'}] {label}")
        if not condition and hint:
            print(f"        -> {hint}")

    chroma_ready = settings.chroma_dir.is_dir() and any(settings.chroma_dir.iterdir())
    cache_ready = settings.fastembed_cache.is_dir() and any(settings.fastembed_cache.iterdir())
    pdfs = sorted(settings.pdf_dir.glob("*.pdf"))

    print("\nConsulta (API):")
    check("Índice ChromaDB en data/index/chroma", chroma_ready, "make ingest, o copia data/index/")
    check("Modelo de embeddings", cache_ready, "se descarga en la primera ingesta")
    check(
        "Dependencias de consulta",
        importlib.util.find_spec("chromadb") is not None,
        "make install",
    )

    print("\nIngesta (opcional, solo si reconstruyes el índice):")
    check("PDF de origen en pdf/", bool(pdfs), f"coloca los PDF en {settings.pdf_dir.resolve()}")
    check(
        "Docling + RapidOCR",
        importlib.util.find_spec("docling") is not None,
        'uv pip install -e ".[ingest]"',
    )

    if chroma_ready and cache_ready:
        print("\nListo para consultar: make serve")
    else:
        print("\nAún no se puede consultar: falta el índice o el modelo de embeddings.")


def cmd_servir(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "vacuinfo.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vacuinfo", description="VacuInfo CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingestar", help="Extracción Docling (OCR) + chunks + índice")
    ingest.add_argument("--fuerza-extraccion", action="store_true")
    ingest.add_argument("--solo-indice", action="store_true")
    ingest.add_argument("--sin-extraccion", action="store_true")
    ingest.add_argument("--sin-indice", action="store_true")
    ingest.set_defaults(func=cmd_ingestar)

    extraer = sub.add_parser("extraer", help="Solo extracción con Docling (layout + OCR)")
    extraer.add_argument("--fuerza", action="store_true")
    extraer.add_argument("--parte", type=int, choices=(1, 2))
    extraer.set_defaults(func=cmd_extraer)

    chunks = sub.add_parser("chunks", help="Solo generación de chunks")
    chunks.set_defaults(func=cmd_chunks)

    indexar = sub.add_parser("indexar", help="Solo indexación en ChromaDB")
    indexar.add_argument("--sin-reiniciar", action="store_true")
    indexar.set_defaults(func=cmd_indexar)

    consultar = sub.add_parser("consultar", help="Pregunta al RAG")
    consultar.add_argument("pregunta")
    consultar.add_argument("-k", type=int, default=6)
    consultar.add_argument("--json", action="store_true")
    consultar.add_argument(
        "--render", action="store_true", help="Renderiza el Markdown en terminal"
    )
    consultar.set_defaults(func=cmd_consultar)

    buscar = sub.add_parser("buscar", help="Solo recuperación, sin LLM")
    buscar.add_argument("consulta")
    buscar.add_argument("-k", type=int, default=6)
    buscar.set_defaults(func=cmd_buscar)

    evaluar = sub.add_parser("evaluar", help="Mide Hit@k sobre un archivo JSONL")
    evaluar.add_argument("--archivo", default="eval/preguntas.jsonl")
    evaluar.add_argument("-k", type=int, default=5)
    evaluar.set_defaults(func=cmd_evaluar)

    servir = sub.add_parser("servir", help="Levanta la API FastAPI")
    servir.add_argument("--host", default="127.0.0.1")
    servir.add_argument("--port", type=int, default=8000)
    servir.add_argument("--reload", action="store_true")
    servir.set_defaults(func=cmd_servir)

    doctor = sub.add_parser("doctor", help="Comprueba qué falta para consultar o ingestar")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
