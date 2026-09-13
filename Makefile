# InterviewOS — developer command shortcuts
# Backend toolchain:  uv   (backend/pyproject.toml + backend/uv.lock)
# Frontend toolchain: npm  (frontend/package.json)

UV      := uv
PY      := $(UV) run python
PYTEST  := $(UV) run pytest
ALEMBIC := $(UV) run alembic

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@echo "InterviewOS make targets:"
	@echo "  make install         - backend uv sync + frontend npm install"
	@echo "  make verify          - full validation gate (compile, pytest, vitest, tsc, build)"
	@echo "  make backend-test    - backend pytest (Alembic-migrated temp DB)"
	@echo "  make backend-compile - compile-check backend + runner sources"
	@echo "  make backend-dev     - backend dev server on :8000 (reload)"
	@echo "  make migrate         - alembic upgrade head"
	@echo "  make migration-new   - new Alembic migration: make migration-new m=slug"
	@echo "  make frontend-check  - TypeScript check (tsc --noEmit)"
	@echo "  make frontend-build  - frontend production build"
	@echo "  make frontend-test   - Vitest unit/component tests (single run)"
	@echo "  make frontend-e2e    - Playwright E2E (docker compose backend + vite, needs docker)"
	@echo "  make frontend-dev    - Vite dev server on :5173"
	@echo "  make docker-up       - docker compose up --build"
	@echo "  make docker-config   - validate docker compose config"
	@echo "  make docker-down     - docker compose down"

.PHONY: install
install: backend-install frontend-install ## Install all dependencies

.PHONY: backend-install
backend-install:
	cd backend && $(UV) sync

.PHONY: backend-compile
backend-compile:
	cd backend && $(PY) -m compileall -q app ../runner

.PHONY: backend-test
backend-test:
	cd backend && $(PYTEST)

.PHONY: backend-dev
backend-dev:
	cd backend && $(UV) run uvicorn app.main:app --reload --port 8000

.PHONY: migrate
migrate:
	cd backend && $(ALEMBIC) upgrade head

.PHONY: migration-new
migration-new:
	cd backend && $(ALEMBIC) revision -m "$(m)"

.PHONY: frontend-install
frontend-install:
	cd frontend && npm install

.PHONY: frontend-check
frontend-check:
	cd frontend && npm run check

.PHONY: frontend-test
frontend-test:
	cd frontend && npm run test:run

.PHONY: frontend-e2e
frontend-e2e:
	cd frontend && npx playwright test

.PHONY: frontend-build
frontend-build:
	cd frontend && npm run build

.PHONY: frontend-dev
frontend-dev:
	cd frontend && npm run dev

.PHONY: verify
verify: backend-compile backend-test frontend-test frontend-check frontend-build ## Full validation gate

.PHONY: docker-up
docker-up:
	docker compose up --build

.PHONY: docker-config
docker-config:
	docker compose config --quiet

.PHONY: docker-down
docker-down:
	docker compose down
