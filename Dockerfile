FROM node:22-bookworm-slim AS web
WORKDIR /build/web
RUN npm install -g pnpm@11.25.0
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build:static

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.txt ./
COPY src/ ./src/
RUN pip install --no-cache-dir --require-hashes -r requirements.txt && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home ignition && mkdir /data && chown ignition /data
COPY --from=web /build/web/out ./web/out
ENV IGNITION_DB=/data/traces.sqlite3 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER ignition
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"
CMD ["uvicorn", "ignition_trace.api:app", "--host", "0.0.0.0", "--port", "8000"]
