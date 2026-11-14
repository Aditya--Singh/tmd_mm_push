# ---- 1. build the React UI ---------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime (works on x86_64 and ARM64 / NVIDIA GB10) -------------
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/backend/data PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# headless Chromium: reads every financial year on RBI's Master Circulars page (the year links are page scripts)
# the browser driver is a Node binary that needs libatomic on ARM64 (GB10)
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*
RUN python -m playwright install --with-deps chromium && chmod -R a+rx /ms-playwright
COPY backend/ .
COPY --from=ui /ui/dist /app/frontend/dist
RUN useradd --create-home --uid 10001 sentinel && mkdir -p /app/backend/data && chown -R sentinel /app
USER sentinel
ENV PORT=8090
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8090\")}/api/health')"
# one worker on purpose: the search index, live event bus and audit-chain lock live in this process
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8090} --proxy-headers --workers 1"]
