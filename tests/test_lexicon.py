from vacuinfo.ingest.lexicon import (
    canonicalize_terms,
    normalize_dose_ordinals,
    normalize_scientific_notation,
    repair_markdown_layout,
)


def test_repair_glued_section_heading():
    text = "Esquema vigente. 6.1.1.8. VACUNA ANTIPOLIOMIELÍTICA ORAL"
    repaired = repair_markdown_layout(text)
    assert "Esquema vigente.\n\n6.1.1.8. VACUNA" in repaired


def test_repair_glued_list_item():
    repaired = repair_markdown_layout("Aplicar según norma: a) primera dosis")
    assert "norma:\na) primera dosis" in repaired


def test_repair_table_row_glued_to_text():
    repaired = repair_markdown_layout("Dosis aplicada. | TIPO | 0.5 ml |")
    assert "Dosis aplicada.\n\n| TIPO | 0.5 ml |" in repaired


def test_repair_does_not_split_table_cells():
    text = "| PRESENTACIÓN | Frasco de 0.5 ml. | Frasco de 1 ml. |"
    assert repair_markdown_layout(text) == text
    text = "| ESQUEMA | Ver 6.1.1.2. Dosis de rescate. |"
    assert repair_markdown_layout(text) == text


def test_tables_are_separated_from_text():
    text = "## Sección\nTexto introductorio.\n| A | B |\n| 1 | 2 |\nCierre."
    repaired = repair_markdown_layout(text)
    assert "Texto introductorio.\n\n| A | B |" in repaired
    assert "| 1 | 2 |\n\nCierre." in repaired


def test_canonicalize_domain_terms():
    assert canonicalize_terms("Vacuna HVB y VHP") == "Vacuna HvB y VPH"
    assert canonicalize_terms("ESAVIS por DTP") == "ESAVI por DPT"
    assert canonicalize_terms("Tdpa y TdaP") == "Tdap y Tdap"
    assert canonicalize_terms("cepa Moscow 361-1") == "cepa Moscow 361-I"
    assert canonicalize_terms("cepa Moscow 361-l") == "cepa Moscow 361-I"


def test_normalize_scientific_notation():
    assert (
        normalize_scientific_notation("1 X 105 del bacilo y 33 X 10⁵ U.F.C.")
        == "1 × 10⁵ del bacilo y 33 × 10⁵ U.F.C."
    )
    assert normalize_scientific_notation("2 × 105 y 8 x 105 UFC") == (
        "2 × 10⁵ y 8 × 10⁵ UFC"
    )
    assert normalize_scientific_notation("2 x 10^5") == "2 × 10⁵"
    assert normalize_scientific_notation("2 x 10 5") == "2 × 10⁵"
    # Sin multiplicación por 10 no se toca el número.
    assert normalize_scientific_notation("1 × 100") == "1 × 100"
    assert normalize_scientific_notation("2 x 105.5") == "2 x 105.5"


def test_normalize_dose_ordinals():
    assert normalize_dose_ordinals("1ra. dosis") == "1ra dosis"
    assert normalize_dose_ordinals("lra dosis") == "1ra dosis"
    assert normalize_dose_ordinals("1.a dosis") == "1ra dosis"
    assert normalize_dose_ordinals("1ª dosis") == "1ra dosis"
    assert normalize_dose_ordinals("2da dosis") == "2da dosis"
    assert normalize_dose_ordinals("3era dosis") == "3ra dosis"
    assert normalize_dose_ordinals("4ta dosis") == "4ta dosis"
    assert normalize_dose_ordinals("1er refuerzo") == "1er refuerzo"
    assert normalize_dose_ordinals("2do refuerzo") == "2do refuerzo"
    assert normalize_dose_ordinals("IRA en niños") == "IRA en niños"
