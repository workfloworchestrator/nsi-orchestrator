# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
#
# Build stage
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:913b757ac0b726679e84b5eb2d400fb4fcd545032116ec92ce8e693fd69abcd7 AS build
ARG VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_NSI_ORCHESTRATOR=${VERSION}
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE README.md *.py ./
COPY products ./products
COPY workflows ./workflows
COPY services ./services
RUN uv build --no-cache --wheel --out-dir dist \
    && uv export --frozen --no-dev --no-emit-project --no-hashes -o dist/requirements.txt

# Final stage
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:913b757ac0b726679e84b5eb2d400fb4fcd545032116ec92ce8e693fd69abcd7
COPY --from=build /app/dist/*.whl /app/dist/requirements.txt /tmp/
# Dependencies come from the exported lock; a fresh resolve picks up releases without a musl wheel.
RUN uv pip install --system --no-cache -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps /tmp/*.whl \
    && rm /tmp/*.whl /tmp/requirements.txt
RUN addgroup -g 1000 orchestrator && adduser -D -u 1000 -G orchestrator orchestrator
USER orchestrator
WORKDIR /home/orchestrator
# Runtime files needed for database migrations and UI translations (not shipped inside the wheel).
COPY --chown=orchestrator:orchestrator alembic.ini ./
COPY --chown=orchestrator:orchestrator migrations ./migrations
COPY --chown=orchestrator:orchestrator translations ./translations
EXPOSE 8080/tcp
CMD ["python", "-m", "uvicorn", "wsgi:app", "--host", "0.0.0.0", "--port", "8080"]
