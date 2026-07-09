# TopoPuzzle Studio — macOS-native dev workflow (Apple Silicon).
# Native execution is the primary path; Docker is optional (see docker-compose.yml).

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/uv pip
API_PORT ?= 8000
WEB_DIR := apps/web

.PHONY: help
help:
	@echo "TopoPuzzle Studio"
	@echo "  make setup      create venv, install Python + web deps"
	@echo "  make dev        run API (:$(API_PORT)) and web (:3000) together"
	@echo "  make api        run the FastAPI backend only"
	@echo "  make web        run the Next.js frontend only"
	@echo "  make test       run the Python test suite"
	@echo "  make lint       ruff check the Python packages"
	@echo "  make examples   regenerate example outputs from synthetic DEMs"
	@echo "  make cli ARGS='generate --geotiff f.tif -o out.zip'"

$(VENV):
	uv venv --python 3.11 $(VENV)

.PHONY: setup
setup: $(VENV)
	$(PIP) install -e "packages/mesh[dev]"
	$(PIP) install -e "apps/api"
	cd $(WEB_DIR) && npm install

.PHONY: api
api:
	$(VENV)/bin/uvicorn app.main:app --app-dir apps/api --reload --port $(API_PORT)

.PHONY: web
web:
	cd $(WEB_DIR) && npm run dev

.PHONY: dev
dev:
	@echo "Starting API on :$(API_PORT) and web on :3000 …"
	@$(VENV)/bin/uvicorn app.main:app --app-dir apps/api --port $(API_PORT) & \
	 cd $(WEB_DIR) && npm run dev & \
	 wait

.PHONY: test
test:
	$(PY) -m pytest tests -q

.PHONY: lint
lint:
	$(VENV)/bin/ruff check packages/mesh/src apps/api/app

.PHONY: examples
examples:
	$(PY) examples/generate_examples.py

.PHONY: cli
cli:
	$(VENV)/bin/topopuzzle $(ARGS)
