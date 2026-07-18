VENV = backend/.venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
BLACK = $(VENV)/bin/black
RUFF = $(VENV)/bin/ruff
UVICORN = $(VENV)/bin/uvicorn

run:
	cd backend && .venv/bin/uvicorn app.main:app --reload

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check app

format:
	cd backend && .venv/bin/black app