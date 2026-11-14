from vacuinfo.rag.retrieve import _field_matches


def test_field_match_conservation():
    text = "6.1.1.10. VACUNA ANTINEUMOCÓCICA — CONSERVACIÓN DE LA VACUNA: +2 °C a +8 °C"
    tokens = {"ambiente", "conservacion", "vacuna", "antineumococica"}
    assert _field_matches(tokens, text) == 1


def test_generic_vaccine_word_does_not_match_a_field():
    text = "6.1.1.10. VACUNA ANTINEUMOCÓCICA — CONSERVACIÓN DE LA VACUNA: +2 °C"
    assert _field_matches({"vacuna"}, text) == 0


def test_multiple_field_matches():
    text = "X — PRESENTACIÓN: frasco. Y — DOSIS (CANTIDAD): 0.5 ml."
    assert _field_matches({"presentacion", "dosis"}, text) == 2


def test_unrelated_text_does_not_match():
    text = "Texto narrativo sobre la vacuna y la población objetivo."
    assert _field_matches({"conservacion"}, text) == 0


def test_field_label_in_section_heading_is_not_a_field_match():
    text = (
        "6.2.2. ESQUEMA DE VACUNACIÓN DE LA NIÑA Y EL NIÑO — EDAD: 2 meses | "
        "TIPO DE VACUNA: Vacuna contra Rotavirus"
    )
    assert _field_matches({"esquema"}, text) == 0
