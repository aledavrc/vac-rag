from vacuinfo.rag.formatting import clip_markdown, format_chunk_markdown


def test_format_inline_bullets_in_field():
    text = "Vacuna X — COMPOSICIÓN: + Antígeno A + Adyuvante B + Conservante C"
    formatted = format_chunk_markdown(text)
    assert "COMPOSICIÓN:" in formatted
    assert "- Antígeno A" in formatted
    assert "- Adyuvante B" in formatted
    assert "- Conservante C" in formatted


def test_format_inline_bullets_in_table_cell():
    text = "| VACUNA | DPT |\n| EVENTO | + Fiebre + Dolor + Eritema |"
    formatted = format_chunk_markdown(text)
    assert "• Fiebre<br>• Dolor" in formatted
    assert "• Eritema" in formatted


def test_format_star_bullets_in_table_cell():
    text = "| ERROR | * Reutilización * Uso * Contaminación |"
    formatted = format_chunk_markdown(text)
    assert "• Reutilización<br>• Uso" in formatted
    assert "• Contaminación" in formatted


def test_clip_markdown_preserves_table_and_lines():
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    clipped = clip_markdown(text, 100)
    assert "| A | B |" in clipped
    assert "| 1 | 2 |" in clipped
    assert clipped.count("\n") == 2


def test_clip_markdown_truncates_at_line_boundary():
    text = "linea uno\nlinea dos\nlinea tres"
    clipped = clip_markdown(text, 15)
    assert clipped.endswith("...")
    assert "linea uno" in clipped
    assert "linea tres" not in clipped
