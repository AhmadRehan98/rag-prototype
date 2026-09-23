FROM python:3.12-slim

WORKDIR /workspace

ARG POETRY_VERSION=2.5

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

ENV POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_PATH=/opt/poetry-venvs \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi

COPY . .

EXPOSE 8000
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]