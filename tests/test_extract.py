from docling.datamodel.pipeline_options import OcrMode, RapidOcrOptions, TesseractCliOcrOptions

from vacuinfo.config import Settings
from vacuinfo.ingest.extract import _ocr_options, pipeline_options


def test_rapidocr_pipeline_options():
    settings = Settings()
    options = pipeline_options(settings)

    assert options.do_ocr is True
    assert options.do_table_structure is True
    assert options.images_scale == 3.0
    assert options.table_structure_options.mode.value == "accurate"
    assert isinstance(options.ocr_options, RapidOcrOptions)
    assert options.ocr_options.lang == ["es"]
    assert options.ocr_options.mode is OcrMode.FULL_PAGE
    assert options.ocr_options.model_size == "medium"


def test_tesseract_cli_maps_language_and_tessdata():
    settings = Settings(ocr_engine="tesseract_cli")
    options = _ocr_options(settings)

    assert isinstance(options, TesseractCliOcrOptions)
    assert options.lang == ["spa"]
    assert options.path.endswith("models/tessdata")
    assert options.mode is OcrMode.FULL_PAGE


def test_unknown_engine_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(ocr_engine="otro")
