.PHONY: install run test lint fmt

install:
	uv sync

run:
	uv run uvicorn app.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
