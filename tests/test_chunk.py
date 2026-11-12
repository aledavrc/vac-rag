import json

from vacuinfo.config import DOC_ID, DOC_TITLE, DocumentSpec, Settings
from vacuinfo.ingest.chunk import (
    _table_structure_flags,
    build_chunks,
    detect_vaccine,
    normalize_field_name,
)


def test_table_flags():
    assert "tabla con columnas duplicadas" in _table_structure_flags(
        [["VACUNA", "DPT", "DPT"], ["EVENTO", "Anafilaxia", "Anafilaxia"]]
    )
    assert "tabla con celdas muy largas" in _table_structure_flags(
        [["CAMPO", "x" * 700]]
    )



def test_detect_vaccine():
    assert detect_vaccine("Vacuna contra el VPH en niñas") == "VPH"
    assert detect_vaccine("6.1.1.8 Vacuna antipoliomielítica oral (APO o Sabin)") == "APO/VOP"
    assert detect_vaccine("Vacuna contra la hepatitis B") == "Hepatitis B"
    assert detect_vaccine("Texto sin nombres de vacunas") is None


def test_normalize_field_name():
    assert normalize_field_name("ION") == "INDICACIÓN"
    assert normalize_field_name("CONTRAINDICACION") == "CONTRAINDICACIÓN"
    assert normalize_field_name("") == "Continuación"


def test_build_chunks(tmp_path):
    settings = Settings(data_dir=tmp_path, models_dir=tmp_path / "models")
    settings.ensure_dirs()
    spec = DocumentSpec(
        doc_id=DOC_ID,
        titulo=DOC_TITLE,
        pdf=tmp_path / "parte-1.pdf",
        part=1,
        page_offset=0,
        pages=1,
    )
    page = """## 6.1.1.8. VACUNA ANTIPOLIO ORAL

Vacuna bivalente que contiene poliovirus vivo atenuado.

| TIPO DE VACUNA | Virus Vivo Atenuado |
|---|---|
| ESQUEMA DE VACUNACIÓN | Dos gotas a los 2 y 4 meses |
| DOSIS (CANTIDAD) | 2 gotas |

## ANEXO 8

| VACUNA | EVENTO | TIEMPO |
|---|---|---|
| DPT | Anafilaxia | 0 a 1 hora |
| SPR | Fiebre | 1 día |
"""
    (settings.processed_dir / f"{spec.stem}.pages.json").write_text(
        json.dumps({"pages": [page]}, ensure_ascii=False),
        encoding="utf-8",
    )

    chunks = build_chunks(settings, (spec,))
    types = {chunk["tipo"] for chunk in chunks}
    assert "ficha_campo" in types
    assert "tabla_completa" in types

    ficha = next(chunk for chunk in chunks if "ESQUEMA DE VACUNACIÓN" in chunk["texto"])
    assert ficha["metadata"]["pagina"] == 1
    assert ficha["metadata"]["vacuna"] == "APO/VOP"
    assert "6.1.1.8" in ficha["metadata"]["seccion"]

    annex = next(chunk for chunk in chunks if "DPT" in chunk["texto"])
    assert annex["metadata"]["vacuna"] == "DTP"
    assert "ANEXO 8" in annex["metadata"]["seccion"]

    lines = settings.chunks_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(chunks)
    assert json.loads(lines[0])["id"]


def test_narrative_uses_section_at_flush_time(tmp_path):
    settings = Settings(data_dir=tmp_path, models_dir=tmp_path / "models")
    settings.ensure_dirs()
    spec = DocumentSpec(
        doc_id=DOC_ID,
        titulo=DOC_TITLE,
        pdf=tmp_path / "parte-1.pdf",
        part=1,
        page_offset=0,
        pages=1,
    )
    page = """## FINALIDAD

Contribuir a disminuir la morbimortalidad causada por enfermedades inmunoprevenibles.

## OBJETIVOS

Establecer el esquema nacional de inmunizaciones para la población.
"""
    (settings.processed_dir / f"{spec.stem}.pages.json").write_text(
        json.dumps({"pages": [page]}, ensure_ascii=False),
        encoding="utf-8",
    )
    chunks = build_chunks(settings, (spec,))
    sections = {chunk["metadata"]["seccion"] for chunk in chunks if chunk["tipo"] == "texto"}
    assert "FINALIDAD" in sections
    assert "OBJETIVOS" in sections
