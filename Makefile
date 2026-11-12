PY := .venv/bin/python

.PHONY: install setup-ocr ingest serve test lint docker-build docker-up docker-down clean-data

install:
	uv venv --python 3.12 .venv
	uv pip install -e ".[ingest,dev]"

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

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean-data:
	rm -rf data/ocr data/processed data/index data/chunks.jsonl data/manifest.json
