FROM python:3.12-slim

ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VACUINFO_DATA_DIR=/app/data \
    VACUINFO_MODELS_DIR=/app/models \
    VACUINFO_EMBEDDING_MODEL=${EMBEDDING_MODEL}

WORKDIR /app

# onnxruntime necesita libgomp; no se instalan herramientas de OCR en runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# El modelo de embeddings se descarga durante el build y queda dentro de la imagen.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}', cache_dir='/app/models/fastembed')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=3)"

CMD ["uvicorn", "vacuinfo.api:app", "--host", "0.0.0.0", "--port", "8000"]
