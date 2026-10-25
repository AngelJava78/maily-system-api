FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN pip install --no-cache-dir "uv==0.13.1"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

# Identificación del build para /info (spec 005, FR-009). Van al final para que un commit nuevo no
# invalide la capa de las dependencias. Sin argumentos quedan vacías y /info publica "unknown".
# APP_ENVIRONMENT no va en la imagen: se inyecta al desplegar.
ARG APP_COMMIT_SHA=""
ARG APP_BUILD_DATE=""
ENV APP_COMMIT_SHA=$APP_COMMIT_SHA \
    APP_BUILD_DATE=$APP_BUILD_DATE

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["alembic", "upgrade", "head"]
