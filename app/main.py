from fastapi import FastAPI
from app.config import settings
from app.routers import transcript
from app.models import HealthResponse, CacheResponse
from app.services.cache_service import CacheService
from app.mcp.server import mcp
from app.middleware.auth import build_mcp_middleware_from_settings
from app.middleware.process_time import ProcessTimeMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize services
cache_service = CacheService()

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

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create main app with MCP lifespan (if available)
app = FastAPI(
    title="YouTube Transcript API",
    description="API service to fetch YouTube video transcripts with metadata and caching",
    version="1.0.0",
    root_path=settings.APP_ROOT_PATH,
    lifespan=mcp_lifespan,  # Pass MCP lifespan to main app
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middleware
app.add_middleware(ProcessTimeMiddleware)

# Include routers
app.include_router(transcript.router, prefix=settings.APP_API_PREFIX)

# Mount MCP HTTP endpoint at /api/v1/mcp
# (mounting is required so the internal Starlette app sees path "/" and not "/api/v1/mcp")
app.mount("/api/v1/mcp", mcp_http_app)


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API information (hidden from Swagger)."""
    return {
        "service": "YouTube Transcript API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": f"{settings.APP_API_PREFIX}/health",
            "transcript": f"{settings.APP_API_PREFIX}/youtube/transcript/{{video_id}}",
            "transcript_raw": f"{settings.APP_API_PREFIX}/youtube/transcript/{{video_id}}/raw",
            "mcp": f"{settings.APP_API_PREFIX}/mcp (StreamableHttpTransport)"
        }
    }


@app.get(f"{settings.APP_API_PREFIX}/health", response_model=HealthResponse, tags=["default"])
async def health_check():
    """Health check endpoint with cache information."""
    return HealthResponse(
        status="healthy"
    )


@app.get(f"{settings.APP_API_PREFIX}/cache", response_model=CacheResponse, tags=["default"])
async def cache_check():
    """Cache check endpoint with cache information."""
    cache_size = cache_service.get_cache_size()
    return CacheResponse(
        status="healthy",
        cache_size=cache_size,
        cache_path=str(cache_service.cache_dir)
    )


def custom_openapi():
    """Custom OpenAPI schema to include MCP endpoint documentation."""
    # Use FastAPI's default OpenAPI generator first
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add MCP endpoint as documentation-only
    openapi_schema["paths"]["/api/v1/mcp"] = {
        "post": {
            "tags": ["MCP"],
            "summary": "MCP Server (Model Context Protocol)",
            "description": """# Model Context Protocol (MCP) Server

This API provides an MCP server endpoint using **StreamableHttpTransport**.

**What is MCP?**
- Open protocol for connecting AI assistants to external data sources
- Allows AI models to call tools/functions exposed by this server
- Learn more: [MCP Documentation](https://modelcontextprotocol.io/)

**Available Tools:**
- `get_youtube_transcript` - Fetch transcript with metadata from YouTube videos
- `clear_cache` - Clear cached transcript for a specific video

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
            arguments={"video_id": "9Wg6tiaar9M", "full_metadata": False}
        )

        # Call a tool - get transcript with full metadata
        result = await session.call_tool(
            "get_youtube_transcript",
            arguments={"video_id": "9Wg6tiaar9M", "full_metadata": True}
        )

        # Call a tool - clear cache
        result = await session.call_tool(
            "clear_cache",
            arguments={"video_id": "9Wg6tiaar9M"}
        )
```

**Note:** This documentation is for reference only.
Actual MCP communication is handled by FastMCP via POST to `/api/v1/mcp`.
Requests use SSE (Server-Sent Events) for real-time bidirectional messaging.
""",
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
