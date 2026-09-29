FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim@sha256:4f5d923c9dcea037f57bda425dd209f3ec643da2f0b74227f68d09dab0b3bb36

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/browser/pyproject.toml services/browser/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
COPY vendor ./vendor
RUN uv sync --frozen --no-dev --package careeract-worker

COPY services ./services

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 careeract

USER careeract

CMD ["uv", "run", "--no-sync", "--package", "careeract-worker", "python", "-m", "services.worker.app.main"]
