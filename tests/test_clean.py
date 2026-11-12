from vacuinfo.ingest.clean import (
    clean_page_markdown,
    looks_like_header,
    normalize_for_match,
    parse_table,
    split_table_row,
)


def test_normalize_for_match():
    assert normalize_for_match("Vacuna contra el VPH") == "vacuna contra el vph"
    assert normalize_for_match("Sarampión, paperas y rubéola") == "sarampion paperas y rubeola"


def test_clean_removes_headers_and_page_numbers():
    page = """<!-- image -->
NTS N° 246 -MINSA/DGIESP-2026
NORMA TÉCNICA DE SALUD QUE ESTABLECE EL ESQUEMA NACIONAL DE INMUNIZACIONES

## 6.1.1.8. VACUNA ANTIPOLIO ORAL

Vacuna bivalente que contiene poliovirus.

22
"""
    cleaned = clean_page_markdown(page)
    assert "MINSA" not in cleaned
    assert "NORMA TÉCNICA" not in cleaned
    assert "<!-- image -->" not in cleaned
    assert cleaned.strip().endswith("poliovirus.")
    assert "6.1.1.8" in cleaned


def test_dehyphenation():
    page = "Las inmuni-\nzaciones son importantes."
    assert "inmunizaciones" in clean_page_markdown(page)


def test_split_table_row_handles_escaped_pipe():
    cells = split_table_row("| JERINGAS A UTILIZAR | &#124; Jeringa precargada |")
    assert cells == ["JERINGAS A UTILIZAR", "Jeringa precargada"]


def test_parse_table_drops_separator():
    rows = parse_table(
        [
            "| CAMPO | VALOR |",
            "|---|---|",
            "| DOSIS | 0,5 ml |",
        ]
    )
    assert rows == [["CAMPO", "VALOR"], ["DOSIS", "0,5 ml"]]


def test_looks_like_header():
    assert looks_like_header(["VACUNA", "EVENTO", "TIEMPO"])
    assert not looks_like_header(["TIPO DE VACUNA", "Virus Vivo Atenuado"])
