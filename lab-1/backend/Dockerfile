# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------------
# Stage 1 — build the virtual environment and bake in the NLP/embedding models.
#
# Models are downloaded at build time, not first-run, so that the running system needs
# no internet access. That matters for the defence: the crawler is the only component
# that should ever reach the network.
# ---------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# build-essential is needed to compile pytrec_eval (dev extra, vendors the NIST
# trec_eval C sources) and as a fallback for any package without a wheel.
RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv && uv venv "$VIRTUAL_ENV"

WORKDIR /build

# Dependency layer, cached independently of application source.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python "$VIRTUAL_ENV/bin/python" -r pyproject.toml

# English linguistic pipeline: lemmatisation, POS tagging and NER.
RUN python -m spacy download en_core_web_sm

# Dense-embedding model for the semantic ranker. ONNX only — no torch.
ARG BAKE_SEMANTIC_MODEL=1
ENV FASTEMBED_CACHE_PATH=/models/fastembed
RUN mkdir -p /models/fastembed && \
    if [ "$BAKE_SEMANTIC_MODEL" = "1" ]; then \
        python -c "\
from fastembed import TextEmbedding; \
m = TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/models/fastembed'); \
v = next(iter(m.embed(['warm the cache']))); \
print('baked embedding model, dim =', len(v))"; \
    else \
        echo 'skipping semantic model bake (BAKE_SEMANTIC_MODEL=0)'; \
    fi

# Application source, installed last so code edits do not invalidate the layers above.
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-deps -e .

# ---------------------------------------------------------------------------------
# Stage 2 — development image: adds the test and lint toolchain.
#
# Separate from `runtime` so the production image carries no test dependencies, and so
# `pytest`/`ruff`/`mypy` are baked in rather than pip-installed on every invocation.
# Runs as root: the virtualenv is root-owned, and this image never faces a network.
# ---------------------------------------------------------------------------------
FROM builder AS dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=test

WORKDIR /app
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python "$VIRTUAL_ENV/bin/python" -r pyproject.toml --extra dev

COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-deps -e .

CMD ["pytest"]

# ---------------------------------------------------------------------------------
# Stage 3 — slim production runtime.
# ---------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/models/fastembed

RUN apt-get update && apt-get install --no-install-recommends -y \
        curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 irs

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /models /models

WORKDIR /app
COPY --from=builder /build/src ./src
COPY --from=builder /build/alembic.ini ./alembic.ini
COPY --from=builder /build/alembic ./alembic
COPY pyproject.toml ./
COPY seeds ./seeds

RUN chown -R irs:irs /app /models
USER irs

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "irs.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
