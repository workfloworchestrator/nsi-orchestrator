# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
#
# Build stage
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:099503f2fe3e97d8b3c0bf972203a18594abf0f546599a04f457c658ee5b3943 AS build
WORKDIR /app
COPY pyproject.toml LICENSE README.md main.py settings.py wsgi.py ./
COPY products ./products
COPY workflows ./workflows
COPY services ./services
RUN uv build --no-cache --wheel --out-dir dist

# Final stage
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:099503f2fe3e97d8b3c0bf972203a18594abf0f546599a04f457c658ee5b3943
COPY --from=build /app/dist/*.whl /tmp/
# git is needed only to fetch the orchestrator-core git dependency (see pyproject); it is added
# transiently and removed so it stays out of the runtime image. Drop it once orchestrator-core is
# pinned to a release again.
RUN apk add --no-cache --virtual .build-deps git \
    && uv pip install --system --no-cache /tmp/*.whl \
    && rm /tmp/*.whl \
    && apk del .build-deps
RUN addgroup -g 1000 orchestrator && adduser -D -u 1000 -G orchestrator orchestrator
USER orchestrator
WORKDIR /home/orchestrator
# Runtime files needed for database migrations and UI translations (not shipped inside the wheel).
COPY --chown=orchestrator:orchestrator alembic.ini ./
COPY --chown=orchestrator:orchestrator migrations ./migrations
COPY --chown=orchestrator:orchestrator translations ./translations
EXPOSE 8080/tcp
CMD ["python", "-m", "uvicorn", "wsgi:app", "--host", "0.0.0.0", "--port", "8080"]
