FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies and the spaCy model live in their own layers: they are ~700 MB of
# wheels and a 55 MB model, and neither changes when application code does.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
RUN python -m spacy download en_core_web_md

COPY alembic.ini pytest.ini ruff.toml mypy.ini ./
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
