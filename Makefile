# Ruta del intérprete del venv según el sistema operativo.
ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
else
  VENV_PY := .venv/bin/python
endif

PY ?= $(VENV_PY)

.PHONY: install setup-ocr ingest serve test lint doctor docker-build docker-up docker-down clean-data

install:
	uv venv --python 3.12 .venv
	uv pip install -e ".[ingest,dev]"

# Solo necesario si se usa VACUINFO_OCR_ENGINE=tesseract_cli.
setup-ocr:
	bash scripts/setup_ocr.sh

ingest:
	$(PY) -m vacuinfo.cli ingestar

serve:
	$(PY) -m vacuinfo.cli servir --reload

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

# Comprueba que un clon nuevo tiene lo mínimo para arrancar.
doctor:
	$(PY) -m vacuinfo.cli doctor

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean-data:
	$(PY) -c "import shutil; from pathlib import Path; [shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True) for p in map(Path, ['data/derived', 'data/ocr', 'data/processed', 'data/index', 'data/chunks.jsonl', 'data/manifest.json'])]"
