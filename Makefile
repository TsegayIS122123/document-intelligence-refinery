.PHONY: help install test lint format clean run-demo docker-build docker-run

help:
	@echo "Available commands:"
	@echo "  install      Install dependencies with uv"
	@echo "  test         Run tests"
	@echo "  lint         Run linters"
	@echo "  format       Format code"
	@echo "  clean        Clean build artifacts"
	@echo "  run-demo     Run demo on sample document"
	@echo "  docker-build Build Docker image"
	@echo "  docker-run   Run with Docker Compose"

install:
	uv sync --dev

test:
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

lint:
	uv run flake8 src/ tests/
	uv run mypy src/

format:
	uv run black src/ tests/
	uv run isort src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run-demo:
	uv run python -m src.cli demo --document data/raw/sample.pdf

docker-build:
	docker build -t document-refinery .

docker-run:
	docker-compose up

.PRECIOUS: .refinery/profiles/%.json