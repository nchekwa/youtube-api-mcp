from fastapi import FastAPI
from contextlib import asynccontextmanager
from time import monotonic
import logging
from pathlib import Path
from fastapi import Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from app.constants import APP_VERSION
from app.config import settings
from app.routers import transcript
from app.routers import transcript_from_audio
from app.middleware.auth import API_KEYS, build_mcp_middleware_from_settings, verify_api_key
from app.models import CacheClearResponse, CacheListResponse, CacheResponse, HealthResponse
from app.mcp.server import mcp
from app.middleware.process_time import ProcessTimeMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.rate_limiter import limiter
from app.services.service_container import get_service_container


logger = logging.getLogger("uvicorn.error")
app_started_at = monotonic()
_default_dependencies = [Depends(verify_api_key)] if API_KEYS else []

_mcp_middleware = build_mcp_middleware_from_settings()

# Get MCP HTTP app with lifespan BEFORE creating main app
# This is required for FastMCP to work properly
mcp_http_app = mcp.http_app(
    path="/",
    stateless_http=True,
    middleware=_mcp_middleware,
)

# Get lifespan from the wrapped app (FastMCP wraps it in _NormalizeEmptyPathASGI)
mcp_lifespan = getattr(mcp_http_app, 'lifespan', None)
if mcp_lifespan is None and hasattr(mcp_http_app, 'app'):
    mcp_lifespan = getattr(mcp_http_app.app, 'lifespan', None)

@asynccontextmanager
async def app_lifespan(app_instance: FastAPI):
    container = get_service_container()
    backend = (settings.APP_TRANSCRIPTION_BACKEND or "").split("#", 1)[0].strip().lower() or "faster-whisper"
    logger.info("Application startup with transcription backend='%s'", backend)
    logger.info(
        "Application startup with transcript_from_audio enabled=%s",
        settings.APP_TRANSCRIPT_FROM_AUDIO,
    )
    container.job_service.mark_stale_jobs_failed()

    if mcp_lifespan is None:
        yield
        return

    async with mcp_lifespan(app_instance):
        yield

# Create main app with MCP lifespan (if available)
app = FastAPI(
    title="YouTube Transcript API",
    description="API service to fetch YouTube video transcripts with metadata and caching",
    version=APP_VERSION,
    root_path=settings.APP_ROOT_PATH,
    lifespan=app_lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middleware
app.add_middleware(ProcessTimeMiddleware)

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.APP_CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.cors_allow_methods or ["*"],
        allow_headers=settings.cors_allow_headers or ["*"],
    )

# Include routers
app.include_router(transcript.router, prefix=settings.APP_API_PREFIX)
app.include_router(transcript_from_audio.router, prefix=settings.APP_API_PREFIX)

# Mount MCP HTTP endpoint at /api/v1/mcp
# (mounting is required so the internal Starlette app sees path "/" and not "/api/v1/mcp")
app.mount("/api/v1/mcp", mcp_http_app)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API information (hidden from Swagger)."""
    return {
        "service": "YouTube Transcript API",
        "version": APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": f"{settings.APP_API_PREFIX}/health",
            "transcript": f"{settings.APP_API_PREFIX}/youtube/transcript/{{video_id}}",
            "transcript_raw": f"{settings.APP_API_PREFIX}/youtube/transcript/raw/{{video_id}}",
            "audio_transcript_request": f"{settings.APP_API_PREFIX}/youtube/audio-transcript/{{video_id}}",
            "audio_transcript_status": f"{settings.APP_API_PREFIX}/youtube/audio-transcript/{{video_id}}",
            "mcp": f"{settings.APP_API_PREFIX}/mcp (StreamableHttpTransport)"
        }
    }


@app.get(f"{settings.APP_API_PREFIX}/health", response_model=HealthResponse, tags=["default"])
async def health_check():
    """Health check endpoint with cache information."""
    container = get_service_container()
    cache_path = Path(container.cache_service.cache_dir)
    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        uptime_seconds=monotonic() - app_started_at,
        transcription_backend=settings.APP_TRANSCRIPTION_BACKEND,
        transcript_from_audio_enabled=settings.APP_TRANSCRIPT_FROM_AUDIO,
        cache_path=str(cache_path),
        cache_accessible=cache_path.exists() and cache_path.is_dir(),
        whisper_model_loaded=container.background_transcription_service.is_model_loaded(),
    )


@app.get(f"{settings.APP_API_PREFIX}/cache", response_model=CacheResponse, tags=["default"])
async def cache_check():
    """Cache check endpoint with cache information."""
    container = get_service_container()
    cache_size = container.cache_service.get_cache_size()
    cache_size_bytes = container.cache_service.get_cache_size_bytes()
    return CacheResponse(
        status="healthy",
        cache_size=cache_size,
        cache_path=str(container.cache_service.cache_dir),
        cache_size_bytes=cache_size_bytes,
        cache_size_mb=container.cache_service.get_cache_size_mb(),
        max_cache_size_mb=settings.APP_MAX_CACHE_SIZE_MB,
    )


@app.get(
    f"{settings.APP_API_PREFIX}/cache/entries",
    response_model=CacheListResponse,
    tags=["default"],
    dependencies=_default_dependencies,
)
@limiter.limit("20/minute")
async def list_cache_entries(request: Request):
    """List all cached transcript entries."""
    del request
    container = get_service_container()
    entries = container.cache_service.list_cache_entries()
    return CacheListResponse(
        status="healthy",
        entries=entries,
        cache_size=container.cache_service.get_cache_size(),
        cache_size_bytes=container.cache_service.get_cache_size_bytes(),
        cache_size_mb=container.cache_service.get_cache_size_mb(),
        max_cache_size_mb=settings.APP_MAX_CACHE_SIZE_MB,
    )


@app.delete(
    f"{settings.APP_API_PREFIX}/cache",
    response_model=CacheClearResponse,
    tags=["default"],
    dependencies=_default_dependencies,
)
@limiter.limit("5/minute")
async def clear_all_cache(request: Request):
    """Clear all cache entries."""
    del request
    container = get_service_container()
    return CacheClearResponse(**container.cache_service.clear_all_cache())


@app.delete(
    f"{settings.APP_API_PREFIX}/cache/{{video_id}}",
    response_model=CacheClearResponse,
    tags=["default"],
    dependencies=_default_dependencies,
)
@limiter.limit("10/minute")
async def clear_cache_entry(request: Request, video_id: str):
    """Clear cache entry for a specific video."""
    del request
    container = get_service_container()
    try:
        normalized_video_id = container.youtube_service.get_video_id(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    result = container.cache_service.clear_cache(normalized_video_id)
    if not result.get("success") and result.get("deleted_entries", 0) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["message"])
    return CacheClearResponse(**result)


def custom_openapi():
    """Custom OpenAPI schema to include MCP endpoint documentation."""
    # Use FastAPI's default OpenAPI generator first
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    clear_cache_tool_doc = ""
    clear_cache_example_doc = ""
    if not settings.APP_MCP_HIDE_CLEAR_CACHE:
        clear_cache_tool_doc = "- `clear_cache` - Clear cached transcript for a specific video\n"
        clear_cache_example_doc = """
        # Call a tool - clear cache
        result = await session.call_tool(
            \"clear_cache\",
            arguments={\"video_id\": \"9Wg6tiaar9M\"}
        )
"""

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    mcp_description = f"""# Model Context Protocol (MCP) Server

This API provides an MCP server endpoint using **StreamableHttpTransport**.

**What is MCP?**
- Open protocol for connecting AI assistants to external data sources
- Allows AI models to call tools/functions exposed by this server
- Learn more: [MCP Documentation](https://modelcontextprotocol.io/)

**Available Tools:**
- `get_youtube_transcript` - Fetch transcript with metadata from YouTube videos
- `request_youtube_audio_transcript` - Queue transcript_from_audio generation using the configured backend
- `get_youtube_audio_transcript` - Check background transcription status by `video_id`
{clear_cache_tool_doc}

**Connection Details:**
- **URL:** `/api/v1/mcp` (mounted at this path)
- **Transport:** StreamableHttpTransport (recommended for production)
- **Authentication:** Requires `X-API-Key` header if configured

**Python Client Example:**
```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_transport

async with streamable_http_transport("http://localhost:8000/api/v1/mcp") as transport:
    async with ClientSession(transport) as session:
        # Initialize connection
        await session.initialize()

        # List available tools
        tools = await session.list_tools()

        # Call a tool - get transcript with basic metadata
        result = await session.call_tool(
            "get_youtube_transcript",
            arguments={{"video_id": "9Wg6tiaar9M"}}
        )
{clear_cache_example_doc}
```

**Note:** This documentation is for reference only.
Actual MCP communication is handled by FastMCP via POST to `/api/v1/mcp`.
Requests use SSE (Server-Sent Events) for real-time bidirectional messaging.
"""

    # Add MCP endpoint as documentation-only
    openapi_schema["paths"]["/api/v1/mcp"] = {
        "post": {
            "tags": ["MCP"],
            "summary": "MCP Server (Model Context Protocol)",
            "description": mcp_description,
            "operationId": "mcp_server",
            "requestBody": {
                "description": "MCP JSON-RPC 2.0 request",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "jsonrpc": {"type": "string", "example": "2.0"},
                                "id": {"type": "integer", "example": 1},
                                "method": {"type": "string", "example": "initialize"},
                                "params": {"type": "object"}
                            },
                            "required": ["jsonrpc", "id", "method"]
                        }
                    }
                },
                "required": True
            },
            "responses": {
                "200": {"description": "MCP response (JSON-RPC)"},
                "307": {"description": "Redirect to /api/v1/mcp/ (SSE endpoint)"}
            }
        }
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
