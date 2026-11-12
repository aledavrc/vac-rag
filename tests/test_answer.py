from vacuinfo.rag.answer import is_answerable
from vacuinfo.rag.retrieve import RetrievedChunk


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        id="x",
        text=text,
        metadata={"pagina": 1, "seccion": "FINALIDAD", "tipo": "texto"},
    )


def test_answerable_when_term_is_present():
    chunks = [_chunk("FINALIDAD Contribuir a disminuir la morbimortalidad.")]
    assert is_answerable("¿Cuál es la finalidad de la norma?", chunks)


def test_abstains_on_price():
    chunks = [_chunk("Vacuna contra el VPH. Esquema de dos dosis.")]
    assert not is_answerable("¿Cuál es el precio de la vacuna contra el VPH?", chunks)


def test_abstains_on_unknown_disease():
    chunks = [_chunk("Vacuna contra la hepatitis A. Composición y dosis.")]
    assert not is_answerable("¿Qué dice la norma sobre la vacuna contra el ébola?", chunks)
