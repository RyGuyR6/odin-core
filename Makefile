run:
	cd backend && .venv/bin/uvicorn app.main:app --reload

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check app

format:
	cd backend && .venv/bin/black app

install:
	cd backend && .venv/bin/pip install -r requirements.txt
