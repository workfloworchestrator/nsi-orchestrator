# syntax=docker/dockerfile:1@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183
#
# Build stage
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:6e3e7a0061d007bf3d7f1b24c258b62f384ef14fbe2df673493d2b53e88b526b AS build
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
FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:6e3e7a0061d007bf3d7f1b24c258b62f384ef14fbe2df673493d2b53e88b526b
# Drops emSign ECC Root CA - G3 (ca-certificates 20261020); remove once the base image has it.
RUN apk upgrade --no-cache ca-certificates ca-certificates-bundle
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
# websockets answers a header line over 8192 bytes with 431; an OIDC session cookie can exceed that.
ENV WEBSOCKETS_MAX_LINE_LENGTH=32768
CMD ["python", "-m", "uvicorn", "wsgi:app", "--host", "0.0.0.0", "--port", "8080"]
