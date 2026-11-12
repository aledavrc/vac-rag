from vacuinfo.ingest.normalize import normalize_clinical_text


def test_normalize_ml_variants():
    assert normalize_clinical_text("0.5 mi")[0] == "0.5 ml"
    assert normalize_clinical_text("9,5 mí")[0] == "9,5 ml"
    assert normalize_clinical_text("1.5mI")[0] == "1.5 ml"
    assert normalize_clinical_text("0.5 mil.")[0] == "0.5 ml."
    assert normalize_clinical_text("2 gotas")[0] == "2 gotas"


def test_normalize_temperature():
    text, flags = normalize_clinical_text("+2'Ca+8%C")
    assert text == "+2 °C a+8 °C"
    assert flags == []


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
