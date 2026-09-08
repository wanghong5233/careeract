FROM ghcr.io/astral-sh/uv:0.11.2-python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/browser/pyproject.toml services/browser/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
COPY vendor ./vendor
RUN uv sync --frozen --no-dev --package careeract-worker

COPY services ./services

RUN useradd --create-home --uid 10001 careeract

USER careeract

CMD ["uv", "run", "--no-sync", "--package", "careeract-worker", "python", "-m", "services.worker.app.main"]
