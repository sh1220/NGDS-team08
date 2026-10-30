FROM python:3.13-slim
# GHCR 패키지를 이 레포에 연결 (GITHUB_TOKEN으로 push하려면 필요)
LABEL org.opencontainers.image.source=https://github.com/sh1220/NGDS-team08

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY catalog ./catalog
COPY scripts/seed_kg.py ./scripts/seed_kg.py

RUN useradd --system --uid 10001 app
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

ENTRYPOINT ["python", "src/server.py"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
