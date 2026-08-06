# Multi-stage build (Section 18): a builder stage with full build tooling,
# and a slim final stage that ships only the built virtualenv and app code.
#
# Migrations are deliberately NOT run here -- `alembic upgrade head` is a
# release/pre-deploy step (Section 18), so a failed migration blocks the
# deploy instead of crash-looping this container. docker-compose.yml runs
# it as a local-dev convenience by overriding the command, not this image.

FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


FROM python:3.12-slim AS final

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
