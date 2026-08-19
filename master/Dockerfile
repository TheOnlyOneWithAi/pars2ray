FROM node:22-alpine AS frontend-build
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY master/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY master/app ./app
COPY --from=frontend-build /src/master/app/static ./app/static
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY deploy/scripts ./scripts
RUN chmod +x scripts/*.sh && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["./scripts/start-master.sh"]
