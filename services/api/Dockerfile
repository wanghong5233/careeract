FROM ghcr.io/astral-sh/uv:0.11.2-python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY vendor ./vendor
RUN uv sync --frozen --no-dev

COPY services ./services

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
