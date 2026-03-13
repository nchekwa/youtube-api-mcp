FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY ./app ./app
RUN mkdir -p /app/cache
EXPOSE 8000

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Metadata
LABEL org.opencontainers.image.title="YouTube Transcript API"
LABEL org.opencontainers.image.description="FastAPI service with MCP integration to fetch YouTube video transcripts with metadata and caching"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/nchekwa/youtube-api-mcp"

# Healthcheck using /api/v1/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${_APP_PORT:-8000}/api/v1/health || exit 1

# Use environment variables for host and port
# Default to 0.0.0.0:8000 if _APP_PORT is not set
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${_APP_PORT:-8000} --log-config /app/app/uvicorn_log_config.json"]
