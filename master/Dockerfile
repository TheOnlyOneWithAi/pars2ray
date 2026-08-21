# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund --prefer-offline
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY master/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-compile -r requirements.txt
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY master/app ./app
COPY --from=frontend-build /src/frontend/dist ./app/static
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY deploy/scripts ./scripts
RUN chmod +x scripts/*.sh && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["./scripts/start-master.sh"]
