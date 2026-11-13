#!/usr/bin/env python3
"""Snapshot reproducible de la ingesta key-value de fichas de vacuna (Fase 1).

Contra `eval/fichas_gold.jsonl` y `data/chunks.jsonl` calcula, por ficha:
  - claves canónicas presentes / esperadas (%),
  - claves no canónicas encontradas,
  - claves esperadas faltantes.
Además imprime un resumen global, un desglose por página, el total de chunks
con clave "Continuación" y ejecuta la evaluación de recuperación existente
(Hit@5). Guarda todo en `data/processed/baseline_fichas.txt`.

Solo biblioteca estándar. No modifica `src/`, `data/chunks.jsonl` ni el índice.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = ROOT / "data" / "chunks.jsonl"
GOLD_PATH = ROOT / "eval" / "fichas_gold.jsonl"
OUT_PATH = ROOT / "data" / "processed" / "baseline_fichas.txt"
PREGUNTAS_PATH = ROOT / "eval" / "preguntas.jsonl"

# Copia literal de KNOWN_FIELDS (src/vacuinfo/ingest/chunk.py). Se mantiene aquí
# para que el script sea autónomo (solo stdlib) y no importe el paquete.
KNOWN_FIELDS = (
    "TIPO DE VACUNA",
    "DESCRIPCIÓN",
    "COMPOSICIÓN",
    "PRESENTACIÓN",
    "INDICACIÓN",
    "ESQUEMA DE VACUNACIÓN",
    "DOSIS (CANTIDAD)",
    "CONSERVACIÓN DE LA VACUNA",
    "VÍA Y SITIO DE ADMINISTRACIÓN",
    "JERINGAS A UTILIZAR",
    "POSIBLES EFECTOS POST-VACUNALES",
    "CONTRAINDICACIÓN",
    "USO SIMULTÁNEO CON OTRAS VACUNAS",
)
KNOWN_SET = set(KNOWN_FIELDS)
SECTION_RE = re.compile(r"6\.1\.1\.(\d+)(?!\d)")
CONTINUACION = "Continuación"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def section_number(text: str | None) -> int | None:
    match = SECTION_RE.search(text or "")
    return int(match.group(1)) if match else None


def chunk_key(chunk: dict) -> str:
    """Extrae la clave de un chunk `ficha_campo` a partir de su texto.

    Formato de origen: ``"<seccion> — <CLAVE>: <valor>"`` (o ``"<CLAVE>: <valor>"``).
    """
    texto = chunk.get("texto", "")
    seccion = chunk.get("seccion") or ""
    prefix = f"{seccion} — " if seccion else ""
    if prefix and texto.startswith(prefix):
        body = texto[len(prefix):]
    elif " — " in texto:
        body = texto.split(" — ", 1)[1]
    else:
        body = texto
    return body.split(": ", 1)[0].strip()


def pct(present: int, expected: int) -> float:
    return (100.0 * present / expected) if expected else 0.0


def build_fichas(chunks: list[dict], gold: list[dict]) -> list[dict]:
    """Asocia chunks a fichas por número de sección (6.1.1.N)."""

    by_section: dict[int, list[dict]] = defaultdict(list)
    for chunk in chunks:
        if chunk.get("tipo") != "ficha_campo":
            continue
        number = section_number(chunk.get("seccion"))
        if number is not None:
            by_section[number].append(chunk)

    fichas: list[dict] = []
    for entry in gold:
        number = section_number(entry.get("seccion"))
        expected = list(entry.get("claves", {}).keys())
        expected_set = set(expected)
        section_chunks = by_section.get(number, [])
        keys_found = [chunk_key(chunk) for chunk in section_chunks]
        canonical_found = {key for key in keys_found if key in KNOWN_SET}
        non_canonical = sorted({key for key in keys_found if key not in KNOWN_SET})
        present = canonical_found & expected_set
        fichas.append(
            {
                "seccion": entry.get("seccion", ""),
                "pagina": entry.get("pagina"),
                "vacuna": entry.get("vacuna", ""),
                "num": number,
                "expected": expected,
                "expected_n": len(expected),
                "present": present,
                "present_n": len(present),
                "missing": sorted(expected_set - canonical_found),
                "extra": sorted(canonical_found - expected_set),
                "non_canonical": non_canonical,
                "chunks": section_chunks,
                "keys_found": keys_found,
            }
        )
    fichas.sort(key=lambda item: (item["num"] is None, item["num"] or 0))
    return fichas


def run_eval() -> tuple[str, str, str | None]:
    python = ROOT / ".venv" / "bin" / "python"
    interpreter = str(python) if python.exists() else sys.executable
    cmd = [
        interpreter,
        "-m",
        "vacuinfo.cli",
        "evaluar",
        "--archivo",
        "eval/preguntas.jsonl",
        "-k",
        "5",
    ]
    display = f"{interpreter} -m vacuinfo.cli evaluar --archivo eval/preguntas.jsonl -k 5"
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=600
        )
        output = (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:  # noqa: BLE001 - la métrica de fichas no debe caerse
        output = f"No se pudo ejecutar la evaluación: {exc}"
    hit_line = next(
        (
            line.strip()
            for line in output.splitlines()
            if re.search(r"Hit@\d+\s*:", line)
        ),
        None,
    )
    return display, output.strip(), hit_line


def _fmt_keys(keys: list[str]) -> str:
    return ", ".join(keys) if keys else "—"


def render(chunks: list[dict], fichas: list[dict]) -> str:
    tipos = Counter(chunk.get("tipo") for chunk in chunks)
    ficha_chunks = [c for c in chunks if c.get("tipo") == "ficha_campo"]
    noncanon_chunks = [c for c in ficha_chunks if chunk_key(c) not in KNOWN_SET]
    continuacion = [c for c in ficha_chunks if chunk_key(c) == CONTINUACION]

    total_expected = sum(ficha["expected_n"] for ficha in fichas)
    total_present = sum(ficha["present_n"] for ficha in fichas)
    exact = sum(1 for ficha in fichas if ficha["present_n"] == ficha["expected_n"])

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append("BASELINE DE INGESTA KEY-VALUE — FICHAS DE VACUNA (Fase 1)")
    lines.append("=" * 80)
    lines.append(f"Chunks:          {len(chunks)}  ({dict(tipos)})")
    lines.append(f"Gold:            {len(fichas)} fichas, {total_expected} claves canónicas esperadas")
    lines.append("Emparejamiento:  por número de sección 6.1.1.N (chunks tipo ficha_campo)")
    lines.append("")

    lines.append("-- Resumen global " + "-" * 62)
    lines.append(
        f"Claves canónicas presentes: {total_present}/{total_expected} "
        f"({pct(total_present, total_expected):.1f}%)"
    )
    lines.append(f"Fichas con todas sus claves presentes: {exact}/{len(fichas)}")
    lines.append(
        f"Chunks ficha_campo: {len(ficha_chunks)} | "
        f"con clave NO canónica: {len(noncanon_chunks)} "
        f"({pct(len(noncanon_chunks), len(ficha_chunks)):.1f}%)"
    )
    lines.append(f"Chunks con clave \"{CONTINUACION}\": {len(continuacion)}")
    lines.append("")

    lines.append("-- Detalle por ficha " + "-" * 59)
    header = f"{'seccion':<62} {'pag':>4} {'pres/esp':>10} {'%':>6}"
    lines.append(header)
    lines.append("-" * len(header))
    for ficha in fichas:
        lines.append(
            f"{ficha['seccion'][:62]:<62} {str(ficha['pagina']):>4} "
            f"{ficha['present_n']:>4}/{ficha['expected_n']:<4} "
            f"{pct(ficha['present_n'], ficha['expected_n']):>6.1f}"
        )
        if ficha["missing"]:
            lines.append(f"    faltantes:      {_fmt_keys(ficha['missing'])}")
        if ficha["non_canonical"]:
            lines.append(f"    no canónicas:   {_fmt_keys(ficha['non_canonical'])}")
        if ficha["extra"]:
            lines.append(f"    extra (canónicas fuera del gold): {_fmt_keys(ficha['extra'])}")
    lines.append("")

    lines.append("-- Desglose por página (página de inicio de cada ficha) " + "-" * 25)
    header = f"{'pag':>4}  {'ficha':<62} {'pres/esp':>10} {'%':>6}"
    lines.append(header)
    lines.append("-" * len(header))
    for ficha in sorted(fichas, key=lambda f: (f["pagina"] is None, f["pagina"] or 0)):
        lines.append(
            f"{str(ficha['pagina']):>4}  {ficha['seccion'][:62]:<62} "
            f"{ficha['present_n']:>4}/{ficha['expected_n']:<4} "
            f"{pct(ficha['present_n'], ficha['expected_n']):>6.1f}"
        )
    lines.append("")

    lines.append("-- Desglose por página (chunks ficha_campo reales) " + "-" * 30)
    by_page: dict[int, list[dict]] = defaultdict(list)
    for chunk in ficha_chunks:
        by_page[chunk.get("pagina")].append(chunk)
    header = f"{'pag':>4}  {'chunks':>6}  {'canón':>5}  {'no canón':>8}  claves no canónicas"
    lines.append(header)
    lines.append("-" * len(header))
    for page in sorted(by_page, key=lambda value: (value is None, value or 0)):
        page_chunks = by_page[page]
        keys = [chunk_key(chunk) for chunk in page_chunks]
        canonical = sorted({key for key in keys if key in KNOWN_SET})
        noncanon = sorted({key for key in keys if key not in KNOWN_SET})
        lines.append(
            f"{str(page):>4}  {len(page_chunks):>6}  {len(canonical):>5}  "
            f"{len(noncanon):>8}  {_fmt_keys(noncanon)}"
        )
    lines.append("")

    display, output, hit_line = run_eval()
    lines.append("-- Evaluación de recuperación (Hit@5) " + "-" * 42)
    lines.append(f"$ {display}")
    lines.append(output if output else "(sin salida)")
    lines.append("")
    lines.append(f"Hit@5 reportado: {hit_line or 'no disponible'}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    chunks = load_jsonl(CHUNKS_PATH)
    gold = load_jsonl(GOLD_PATH)
    fichas = build_fichas(chunks, gold)
    report = render(chunks, fichas)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"[guardado] {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
