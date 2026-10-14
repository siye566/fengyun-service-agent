FROM node:22-bookworm-slim AS console
WORKDIR /build
COPY package.json package-lock.json ./
COPY apps/service-console/package.json apps/service-console/package.json
RUN npm ci --no-audit --no-fund
COPY apps/service-console apps/service-console
RUN NODE_OPTIONS=--max-old-space-size=512 npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend ACS_STATIC_DIR=/app/static
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt && useradd --uid 10001 --create-home acs
COPY backend/acs backend/acs
COPY LICENSE NOTICE.md ./
COPY --from=console /build/apps/service-console/dist /app/static
USER acs
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"
CMD ["python", "-m", "uvicorn", "acs.web:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--limit-concurrency", "24", "--timeout-keep-alive", "5", "--no-proxy-headers"]
