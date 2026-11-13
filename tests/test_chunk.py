import json

from vacuinfo.config import DOC_ID, DOC_TITLE, DocumentSpec, Settings
from vacuinfo.ingest.chunk import (
    _SECTION_HEADING,
    KNOWN_FIELDS,
    _is_ficha,
    _table_structure_flags,
    _value_columns,
    build_chunks,
    detect_vaccine,
    normalize_field_name,
)


def _chunks_from_pages(tmp_path, pages: list[str]):
    settings = Settings(data_dir=tmp_path, models_dir=tmp_path / "models")
    settings.ensure_dirs()
    spec = DocumentSpec(
        doc_id=DOC_ID,
        titulo=DOC_TITLE,
        pdf=tmp_path / "parte-1.pdf",
        part=1,
        page_offset=0,
        pages=len(pages),
    )
    (settings.processed_dir / f"{spec.stem}.pages.json").write_text(
        json.dumps({"pages": pages}, ensure_ascii=False),
        encoding="utf-8",
    )
    return build_chunks(settings, (spec,))


def _chunks_from_page(tmp_path, page: str):
    return _chunks_from_pages(tmp_path, [page])


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


def test_normalize_field_name_ocr_fixes():
    # Correcciones explícitas no ambiguas de la Fase 2.
    fixes = {
        "E": "CONSERVACIÓN DE LA VACUNA",
        "INCAS A": "JERINGAS A UTILIZAR",
        "¿ POST RES": "POSIBLES EFECTOS POST-VACUNALES",
        "CONSERVACIÓN DE": "CONSERVACIÓN DE LA VACUNA",
        "CONSERVACIÓN DE -": "CONSERVACIÓN DE LA VACUNA",
        "ADMINISTRACIÓN VIA Y SITIO DE": "VÍA Y SITIO DE ADMINISTRACIÓN",
        "SIMULTÁNEO OTRAS USO CON VACUNAS": "USO SIMULTÁNEO CON OTRAS VACUNAS",
        "ESQUEMA": "ESQUEMA DE VACUNACIÓN",
    }
    for raw, expected in fixes.items():
        assert normalize_field_name(raw) == expected


def test_normalize_field_name_fuzzy():
    # rapidfuzz: reordenamiento, truncamiento y palabras partidas.
    assert normalize_field_name("ESQUEMA DE Cc CIÓN VACUNACIO") == "ESQUEMA DE VACUNACIÓN"
    assert normalize_field_name("PRESENT ACIÓN") == "PRESENTACIÓN"
    assert normalize_field_name("CONTRAINDIC ACIÓN") == "CONTRAINDICACIÓN"
    assert normalize_field_name("La COMPOSICIÓN") == "COMPOSICIÓN"
    assert normalize_field_name("CONSERVACIÓNDE LA VACUNA") == "CONSERVACIÓN DE LA VACUNA"


def test_normalize_field_name_strips_section_prefix():
    assert (
        normalize_field_name("6.1.1.6. VACUNA CONTRA TIPO DE VACUNA")
        == "TIPO DE VACUNA"
    )


def test_normalize_field_name_ambiguous_stays_unresolved():
    # No se inventan mapeos: el caller las marca para revisión.
    for raw in ("CO CUBACIÓN", "A STR ÓN DE -_", "ÓN Ag NEO VACUNAS", "CONSERVACIÓN"):
        assert normalize_field_name(raw) == raw


def test_normalize_field_name_canonical_identity():
    for field in KNOWN_FIELDS:
        assert normalize_field_name(field) == field


def test_build_chunks_marks_unresolved_field(tmp_path):
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
    page = """## 6.1.1.23. VACUNA MENINGOCOCO

| TIPO DE VACUNA | Conjugada |
|---|---|
| ESQUEMA DE VACUNACIÓN | Dos dosis |
| CO CUBACIÓN | 02 dosis |
"""
    (settings.processed_dir / f"{spec.stem}.pages.json").write_text(
        json.dumps({"pages": [page]}, ensure_ascii=False),
        encoding="utf-8",
    )

    chunks = build_chunks(settings, (spec,))
    unresolved = next(chunk for chunk in chunks if "CO CUBACIÓN" in chunk["texto"])
    assert unresolved["metadata"]["revisar"] is True
    assert "clave no canónica" in unresolved["metadata"]["notas"]

    resolved = next(chunk for chunk in chunks if "ESQUEMA DE VACUNACIÓN" in chunk["texto"])
    assert not resolved["metadata"].get("revisar")


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


def test_section_heading_without_hash():
    assert _SECTION_HEADING.match("6.1.1.10. VACUNA ANTINEUMOCÓCICA (*)")
    assert _SECTION_HEADING.match("6.1.1.20. VACUNA CONTRA INFLUENZA")
    assert not _SECTION_HEADING.match(
        "Ver: Dosis de rescate en Anexo 2 y casos especiales en ítem 6.3"
    )
    assert not _SECTION_HEADING.match("ver esquema en el numeral 6.2.1")


def test_is_ficha_and_value_columns():
    ficha = [
        ["TIPO DE VACUNA", "Inactivado", "Inactivado"],
        ["DESCRIPCIÓN", "Texto", "Texto"],
        ["COMPOSICIÓN", "Vacuna", "Vacuna"],
    ]
    assert _is_ficha(ficha)
    assert _value_columns(ficha) == [1, 2]

    datos = [
        ["EDAD GESTACIONAL", "TIPO DE VACUNA", "DOSIS"],
        ["Embarazo de 20 a 36 semanas", "Tdap", "01 dosis"],
    ]
    assert not _is_ficha(datos)

    anti_vrs = [
        ["TIPO INMUNIZACIÓN", "DE", "Inmunización pasiva"],
        ["DESCRIPCIÓN", "", "Está clasificado"],
        ["COMPOSICIÓN", "", "Solución inyectable"],
        ["PRESENTACIÓN", "", "Jeringa precargada"],
    ]
    assert _is_ficha(anti_vrs)
    assert _value_columns(anti_vrs) == [2]


def test_build_chunks_page14_hep_b_three_columns(tmp_path):
    page = """## 6.1.1.2. VACUNA CONTRA HEPATITIS B (HvB)

| TIPO DE VACUNA | Inactivado recombinante | Inactivado recombinante |
|---|---|---|
| DESCRIPCIÓN | Antígeno de superficie (HBsAg). | Antígeno de superficie (HBsAg). |
| COMPOSICIÓN | Vacuna Pediátrica | Vacuna para Adulto |
| PRESENTACIÓN | Frasco Monodosis de 0.5 ml. | Frasco Monodosis de 1 ml. |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]
    assert fichas
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.2") for chunk in fichas)
    assert all(chunk["metadata"]["vacuna"] == "Hepatitis B" for chunk in fichas)
    assert not any(chunk["tipo"] == "tabla_completa" for chunk in chunks)

    tipo = next(chunk for chunk in fichas if "TIPO DE VACUNA" in chunk["texto"])
    # Columnas duplicadas: se colapsa a un único valor.
    assert "TIPO DE VACUNA: Inactivado recombinante" in tipo["texto"]

    composicion = next(chunk for chunk in fichas if "COMPOSICIÓN" in chunk["texto"])
    # Columnas con variantes: se unen con " | ".
    assert "Vacuna Pediátrica | Vacuna para Adulto" in composicion["texto"]


def test_build_chunks_page24_antineumococo_plain_heading(tmp_path):
    page = """6.1.1.10. VACUNA ANTINEUMOCÓCICA (*)

| TIPO DE VACUNA | Inactivado Conjugada | Inactivado Conjugada |
|---|---|---|
| DESCRIPCIÓN | Previene infecciones invasivas graves. | Previene infecciones invasivas graves. |
| COMPOSICIÓN | Vacuna PCV 20. | Vacuna PCV 20. |
| PRESENTACIÓN | Monodosis. Frasco de 0.5 ml. | Monodosis. Frasco de 0.5 ml. |
| INDICACIÓN | Prevención de enfermedades invasivas. | Prevención de enfermedades invasivas. |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]
    assert fichas
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.10") for chunk in fichas)
    assert all(chunk["metadata"]["vacuna"] == "Neumococo" for chunk in fichas)
    assert not any(chunk["tipo"] == "tabla_completa" for chunk in chunks)


def test_build_chunks_page37_influenza_plain_heading(tmp_path):
    page = """6.1.1.20. VACUNA CONTRA INFLUENZA

| TIPO DE VACUNA | Virus iInactivado | Virus iInactivado |
|---|---|---|
| DESCRIPCIÓN | Confiere inmunidad contra serotipos. | Confiere inmunidad contra serotipos. |
| COMPOSICIÓN | Vacuna trivalente. | Vacuna trivalente. |
| PRESENTACIÓN | Vacuna monodosis. | Vacuna monodosis. |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]
    assert fichas
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.20") for chunk in fichas)
    assert all(chunk["metadata"]["vacuna"] == "Influenza" for chunk in fichas)
    assert not any(chunk["tipo"] == "tabla_completa" for chunk in chunks)


def test_build_chunks_page43_anti_vrs_junk_column(tmp_path):
    page = """## 6.1.1.24. INMUNIZACIÓN CON ANTICUERPO MONOCLONAL CONTRA EL VRS

| TIPO INMUNIZACIÓN | DE | Inmunización pasiva con anticuerpo monoclonal Nirsevimab |
|---|---|---|
| DESCRIPCIÓN | | Anticuerpo monoclonal de acción prolongada. |
| COMPOSICIÓN | | Solución inyectable sin preservantes. |
| PRESENTACIÓN | | Jeringa precargada |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]
    assert fichas
    assert not any(chunk["tipo"] == "tabla_completa" for chunk in chunks)

    tipo = next(chunk for chunk in fichas if "TIPO DE VACUNA" in chunk["texto"])
    assert "TIPO DE VACUNA: Inmunización pasiva" in tipo["texto"]
    assert "DE |" not in tipo["texto"]


def test_build_chunks_pentavalente_merges_split_continuations(tmp_path):
    # Caso real p.17-19: ficha partida con continuaciones cross-página e intra-página.
    pages = [
        """## 6.1.1.4. VACUNA COMBINADA PENTAVALENTE (DPT-HvB-Hib) (*)

| TIPO DE VACUNA | inactivados |
| DESCRIPCIÓN | Vacuna combinada, contiene células enteras de Bordetella pertussis. |
""",
        """| | El componente de suspensión de pertussis se obtiene de cultivos. |
| COMPOSICIÓN | Cada dosis de 0.5 ml contiene toxoide diftérico. |
| PRESENTACIÓN | Frasco monodosis de 0.5 ml. |
| INDICACIÓN | Prevención de la difteria y el tétanos. |
| ESQUEMA DE VACUNACIÓN | Tres dosis a los 2, 4 y 6 meses. |
| DOSIS (CANTIDAD) CONSERVACIÓN DE LA VACUNA | 0.5 ml. |
| | +2Ca+8 °C Frasco abierto: su uso es inmediato |
| VÍA Y SITIO DE ADMINISTRACIÓN | Intramuscular. |
| JERINGAS A UTILIZAR | Jeringa descartable de 1 ml. |
| POSIBLES EFECTOS POST-VACUNALES | Reacciones locales: |
""",
        """| | Dolor, enrojecimiento en el lugar de la aplicación. |
| CONTRAINDICACIÓN | Reacción alérgica a dosis previas. |
| USO SIMULTÁNEO CON OTRAS VACUNAS | Puede ser aplicada simultáneamente. |
""",
    ]
    chunks = _chunks_from_pages(tmp_path, pages)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    # Las continuaciones se absorben: no queda ninguna clave "Continuación".
    assert not any("Continuación" in chunk["texto"] for chunk in fichas)
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.4") for chunk in fichas)

    descripcion = next(chunk for chunk in fichas if "DESCRIPCIÓN" in chunk["texto"])
    assert "contiene células enteras de Bordetella pertussis" in descripcion["texto"]
    assert "El componente de suspensión de pertussis" in descripcion["texto"]

    efectos = next(
        chunk for chunk in fichas if "POSIBLES EFECTOS POST-VACUNALES" in chunk["texto"]
    )
    assert "Reacciones locales: Dolor, enrojecimiento" in efectos["texto"]

    # Continuación intra-página de una clave fusionada (DOSIS + CONSERVACIÓN).
    dosis = next(
        chunk for chunk in fichas if "DOSIS (CANTIDAD) CONSERVACIÓN" in chunk["texto"]
    )
    assert "0.5 ml." in dosis["texto"]
    assert "+2Ca+8 °C Frasco abierto" in dosis["texto"]

    # Los campos ajenos al corte no se contaminan.
    composicion = next(chunk for chunk in fichas if "COMPOSICIÓN" in chunk["texto"])
    assert "contiene células enteras" not in composicion["texto"]


def test_build_chunks_spr_split_at_field_boundaries_no_merge(tmp_path):
    # Caso real p.25-27: ficha partida en límites de campo, sin continuaciones.
    pages = [
        """## 6.1.1.11. VACUNA CONTRA SARAMPIÓN, PAPERAS Y RUBEOLA (SPR)

| TIPO DE VACUNA | Virus Vivos Atenuados |
| DESCRIPCIÓN | Preparadas en cepas vivas atenuadas del virus del sarampión. |
""",
        """| COMPOSICIÓN | La vacuna contiene 1000 DICCs del virus de sarampión. |
| PRESENTACIÓN | Frasco liofilizado con diluyente de 0.5 ml. |
| INDICACIÓN | Prevención del Sarampión, Rubeola y Parotiditis. |
""",
        """| ESQUEMA DE VACUNACIÓN | Dos dosis: 12 meses y 18 meses de edad. |
| DOSIS (CANTIDAD) | 0.5 ml |
| USO SIMULTÁNEO CON OTRAS VACUNAS | Se puede administrar simultáneamente. |
""",
    ]
    chunks = _chunks_from_pages(tmp_path, pages)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    # Ficha reconstruida en 8 campos, sin fusiones ni continuaciones.
    assert len(fichas) == 8
    assert not any("Continuación" in chunk["texto"] for chunk in fichas)
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.11") for chunk in fichas)

    descripcion = next(chunk for chunk in fichas if "DESCRIPCIÓN" in chunk["texto"])
    assert descripcion["texto"].endswith(
        "Preparadas en cepas vivas atenuadas del virus del sarampión."
    )
    composicion = next(chunk for chunk in fichas if "COMPOSICIÓN" in chunk["texto"])
    assert composicion["texto"].endswith(
        "La vacuna contiene 1000 DICCs del virus de sarampión."
    )


def test_build_chunks_sr_does_not_merge_with_previous_ficha(tmp_path):
    # Caso real p.27-28: SPR y SR son fichas distintas; el reinicio en
    # TIPO DE VACUNA y la sección diferente impiden fusionarlas.
    pages = [
        """## 6.1.1.11. VACUNA CONTRA SARAMPIÓN, PAPERAS Y RUBEOLA (SPR)

| TIPO DE VACUNA | Virus Vivos Atenuados |
| USO SIMULTÁNEO CON OTRAS VACUNAS | Se puede administrar simultáneamente con SPR. |
""",
        """## 6.1.1.12. VACUNA CONTRA SARAMPIÓN Y RUBEOLA (SR)

| TIPO DE VACUNA | Virus vivos atenuados |
| DESCRIPCIÓN | Preparadas en cepas vivas atenuadas del virus del sarampión. |
""",
    ]
    chunks = _chunks_from_pages(tmp_path, pages)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    spr_uso = next(chunk for chunk in fichas if "USO SIMULTÁNEO" in chunk["texto"])
    sr_tipo = next(
        chunk
        for chunk in fichas
        if chunk["metadata"]["seccion"].startswith("6.1.1.12")
        and "TIPO DE VACUNA" in chunk["texto"]
    )

    assert spr_uso["metadata"]["seccion"].startswith("6.1.1.11")
    assert sr_tipo["metadata"]["seccion"].startswith("6.1.1.12")
    assert "Preparadas en cepas vivas atenuadas" not in spr_uso["texto"]
    assert "Se puede administrar simultáneamente con SPR" not in sr_tipo["texto"]
    assert sr_tipo["texto"].endswith("Virus vivos atenuados")


def test_build_chunks_control_negative_single_page_ficha(tmp_path):
    # Control negativo: ficha no partida; ningún campo se fusiona.
    page = """## 6.1.1.2. VACUNA CONTRA HEPATITIS B (HvB)

| TIPO DE VACUNA | Inactivado recombinante |
| DESCRIPCIÓN | Antígeno de superficie (HBsAg). |
| COMPOSICIÓN | Vacuna Pediátrica, 10 mcg. |
| PRESENTACIÓN | Frasco Monodosis de 0.5 ml. |
| INDICACIÓN | Prevención de la hepatitis B. |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    assert len(fichas) == 5
    assert not any("Continuación" in chunk["texto"] for chunk in fichas)
    assert all(chunk["metadata"]["seccion"].startswith("6.1.1.2") for chunk in fichas)

    presentacion = next(chunk for chunk in fichas if "PRESENTACIÓN" in chunk["texto"])
    assert presentacion["texto"].endswith("Frasco Monodosis de 0.5 ml.")


def test_build_chunks_continuation_survives_residual_header_texto(tmp_path):
    # Casos reales p.33-34: un encabezado/pie residual se cuela como chunk
    # "texto" entre el campo y su continuación; no debe romper la ficha.
    pages = [
        """## 6.1.1.16. VACUNA CONTRA DIFTERIA Y TÉTANOS (dT ADULTO)

| TIPO DE VACUNA | Inactivadas |
| ESQUEMA DE VACUNACIÓN | 1ra dosis al primer contacto. |
""",
        """NISN* 2/6 NINSAMGIESP-2026 NORMA TÉCNICA DE SALUD

| | Sradosis a los 6 meses de la primera dosis. |
| DOSIS (CANTIDAD) | 5 ml |
| CONSERVACIÓN DE LA VACUNA | +2 °C a +8 °C. |
| CONTRAINDICACIÓN | Hipersensibilidad. |
""",
    ]
    chunks = _chunks_from_pages(tmp_path, pages)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    assert not any("Continuación" in chunk["texto"] for chunk in fichas)
    esquema = next(chunk for chunk in fichas if "ESQUEMA DE VACUNACIÓN" in chunk["texto"])
    assert "Sradosis a los 6 meses de la primera dosis" in esquema["texto"]


def test_build_chunks_orphan_continuation_is_kept_and_flagged(tmp_path):
    # Sin campo previo en la sección no se infiere la clave (ADR-004).
    page = """## 6.1.1.20. VACUNA CONTRA INFLUENZA

| | Texto que continúa algo que no existe. |
| DESCRIPCIÓN | Vacuna trivalente. |
| COMPOSICIÓN | Vacuna inactivada. |
"""
    chunks = _chunks_from_page(tmp_path, page)
    fichas = [chunk for chunk in chunks if chunk["tipo"] == "ficha_campo"]

    orphan = next(chunk for chunk in fichas if "Continuación" in chunk["texto"])
    assert orphan["metadata"]["revisar"] is True
    assert "continuación sin campo previo" in orphan["metadata"]["notas"]
