# Stage 1: Builder
FROM python:3.11-slim as builder
WORKDIR /app
RUN pip install --upgrade pip
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels .[server]

# Stage 2: Runner
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/*
CMD ["uvicorn", "open_skill_registry.server.main:app", "--host", "0.0.0.0", "--port", "8000"]
