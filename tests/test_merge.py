from vacuinfo.ingest.merge import (
    block_kind,
    is_table_note,
    merge_page_pair,
    merge_pages,
    split_blocks,
)

TABLE_A = """| VACUNA | EVENTO | TASA |
| DPT | Anafilaxia | 20 por millón |
| DPT | Convulsiones | 1 por millón |"""

TABLE_B = """| VACUNA | EVENTO | TASA |
| DPT | Llanto persistente | 100 por millón |
| DPT | Fiebre alta | 50 por millón |"""

FICHA_A = """| TIPO DE VACUNA | Inactivado |
| COMPOSICIÓN | Antígeno de superficie. |"""


def test_split_blocks_and_kinds():
    blocks = split_blocks("# Título\n\n| a | b |\n\nTexto.")
    assert [block_kind(block) for block in blocks] == ["heading", "table", "text"]


def test_merge_tables_across_pages():
    previous = f"## ANEXO 8. TASAS DE ESAVI\n\n{TABLE_A}"
    nxt = TABLE_B

    left, right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is True
    assert not right
    assert "Llanto persistente" in left
    assert left.count("| VACUNA | EVENTO | TASA |") == 1


def test_duplicate_header_is_removed():
    previous = "| VACUNA | EVENTO |\n| DPT | A |"
    nxt = "| VACUNA | EVENTO |\n| DPT | B |"

    left, _right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is True
    assert left.count("| VACUNA | EVENTO |") == 1
    assert "| DPT | B |" in left


def test_ficha_tables_are_not_moved_between_pages():
    previous = FICHA_A
    nxt = "| PRESENTACIÓN | Frasco monodosis. |\n| DOSIS (CANTIDAD) | 0.5 ml. |"

    left, right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is False
    assert left == previous
    assert right == nxt


def test_different_column_count_is_not_merged():
    previous = TABLE_A
    nxt = "| A | B |\n| 1 | 2 |"

    left, right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is False
    assert right == nxt


def test_new_ficha_is_not_merged():
    previous = TABLE_A
    nxt = FICHA_A

    _left, right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is False
    assert right == nxt


def test_new_ficha_mid_block_splits_the_table():
    previous = "| VACUNA | EVENTO |\n| DPT | A |"
    nxt = """| DPT | B |
| TIPO DE VACUNA | Virus vivo |
| OTRO | C |"""

    left, right, events = merge_page_pair(previous, nxt)
    assert events["tabla"] is True
    assert "| DPT | B |" in left
    assert "TIPO DE VACUNA | Virus vivo" in right
    assert "TIPO DE VACUNA | Virus vivo" not in left


def test_table_notes_are_moved_to_previous_page():
    previous = "## 6.1.1.10. VACUNA ANTINEUMOCÓCICA\n\n| TIPO DE VACUNA | Conjugada |"
    nxt = "(*) Vacuna incluida en el esquema.\n\nTexto posterior."

    left, right, events = merge_page_pair(previous, nxt)
    assert events["nota"] is True
    assert "(*) Vacuna incluida" in left
    assert right == "Texto posterior."


def test_paragraph_continuation_is_joined():
    previous = "## 6.1.1.2. VACUNA\n\nLa vacuna se aplica por vía intramuscular en el"
    nxt = "deltoides, según el esquema nacional."

    left, right, events = merge_page_pair(previous, nxt)
    assert events["parrafo"] is True
    assert "en el deltoides" in left
    assert not right


def test_paragraph_with_closing_punctuation_is_not_joined():
    previous = "## 6.1.1.2. VACUNA\n\nLa vacuna se aplica por vía intramuscular."
    nxt = "Otro párrafo completo de la página siguiente."

    _left, right, events = merge_page_pair(previous, nxt)
    assert events["parrafo"] is False
    assert right == nxt


def test_heading_prevents_paragraph_merge():
    previous = "## 6.1.1.2. VACUNA\n\nLa vacuna se aplica en el brazo y"
    nxt = "## 6.1.1.3. OTRA VACUNA\n\nTexto nuevo."

    _left, right, events = merge_page_pair(previous, nxt)
    assert events["parrafo"] is False
    assert right == nxt


def test_merge_pages_respects_skip():
    pages = [
        "## 6.1.1.2. VACUNA\n\n| A | B |",
        "| C | D |",
    ]
    merged, reports = merge_pages(pages, skip={2})
    assert merged == pages
    assert reports == []


def test_is_table_note():
    assert is_table_note("(1) Dosis de rescate.")
    assert is_table_note("(*) Vacuna del esquema.")
    assert is_table_note("Nota: no congelar.")
    assert not is_table_note("Texto normal del párrafo.")
    assert not is_table_note("| a | b |")
