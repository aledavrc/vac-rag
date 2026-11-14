from vacuinfo.ingest.normalize import normalize_clinical_text


def test_normalize_ml_variants():
    assert normalize_clinical_text("0.5 mi")[0] == "0.5 ml"
    assert normalize_clinical_text("9,5 mí")[0] == "9,5 ml"
    assert normalize_clinical_text("1.5mI")[0] == "1.5 ml"
    assert normalize_clinical_text("0.5 mil.")[0] == "0.5 ml."
    assert normalize_clinical_text("2 gotas")[0] == "2 gotas"


def test_normalize_temperature():
    text, flags = normalize_clinical_text("+2'Ca+8%C")
    assert text == "+2 °C a +8 °C"
    assert flags == []


def test_normalize_broken_cold_chain_range():
    assert (
        normalize_clinical_text("+20C a +80C")[0]
        == "+2 °C a +8 °C"
    )
    assert normalize_clinical_text("+2 oC a +8 oC")[0] == "+2 °C a +8 °C"
    assert normalize_clinical_text("2°C a 8°C")[0] == "+2 °C a +8 °C"
    assert normalize_clinical_text("+2º C")[0] == "+2 °C"
    assert normalize_clinical_text("+ 2℃ a +8℃")[0] == "+2 °C a +8 °C"
    assert normalize_clinical_text("+2° a +8 °C")[0] == "+2 °C a +8 °C"
    assert normalize_clinical_text("+8°℃")[0] == "+8 °C"


def test_day_ordinal_is_not_a_temperature():
    text, _flags = normalize_clinical_text("Se manifiesta a partir del 5° día a 30 días.")
    assert "5° día" in text


def test_compact_temperature_uses_context():
    text, flags = normalize_clinical_text("Conservar entre +20C y +80C")
    assert text == "Conservar entre +2 °C y +8 °C"
    assert flags == []


def test_compact_temperature_without_context_is_flagged():
    text, flags = normalize_clinical_text("La sala estaba a +20C")
    assert "+20C" in text
    assert "temperatura dudosa: +20C" in flags


def test_negative_temperature_is_not_touched():
    text, _flags = normalize_clinical_text("Congelar a -20C")
    assert "-20C" in text
    text, _flags = normalize_clinical_text("-20C a -80C")
    assert "-20 °C a -80 °C" in text


def test_ocr_volume_variants():
    assert normalize_clinical_text("O,5 ml")[0] == "0.5 ml"
    assert normalize_clinical_text("0,5ml")[0] == "0.5 ml"
    assert normalize_clinical_text("0.5 m1")[0] == "0.5 ml"
    assert normalize_clinical_text("O,1 ml")[0] == "0.1 ml"


def test_scientific_notation_in_clinical_text():
    text, _flags = normalize_clinical_text("1 X 105 del bacilo y 8 x 105 UFC")
    assert text == "1 × 10⁵ del bacilo y 8 × 10⁵ UFC"


def test_missing_decimal_is_flagged_not_corrected():
    text, flags = normalize_clinical_text("DOSIS (CANTIDAD): 05 ml")
    assert "05 ml" in text
    assert "posible decimal perdido: 05" in flags


def test_non_numeric_dose_is_flagged():
    text, flags = normalize_clinical_text("DOSIS (CANTIDAD): Di5ami")
    assert text == "DOSIS (CANTIDAD): Di5ami"
    assert "dosis con formato dudoso" in flags


def test_normal_text_is_unchanged():
    text, flags = normalize_clinical_text("La vacuna se aplica en el brazo.")
    assert text == "La vacuna se aplica en el brazo."
    assert flags == []
