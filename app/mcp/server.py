from fastmcp import FastMCP
from app.config import settings
from starlette.middleware import Middleware
from app.middleware.auth import MCPAPIKeyMiddleware, build_mcp_middleware_from_settings
from app.services.youtube_service import YouTubeService
from app.services.cache_service import CacheService

# Initialize services
youtube_service = YouTubeService()
cache_service = CacheService()


def _extract_basic_metadata(metadata: dict) -> dict:
    """Extract basic fields from full metadata."""
    return {
        "title": metadata.get("title", "Unknown"),
        "author": metadata.get("author", "Unknown"),
        "duration": metadata.get("duration", 0),
        "publish_date": metadata.get("upload_date", "Unknown"),
        "view_count": metadata.get("view_count", 0),
        "thumbnail": metadata.get("thumbnail"),
        "description": metadata.get("description")
    }


# Create MCP server
mcp = FastMCP("YouTube Transcript API")


@mcp.tool()
def get_youtube_transcript(video_id: str) -> str:
    """
    Get transcript from a YouTube video (first available language).

    Args:
        video_id: YouTube video ID (11 characters) or full URL (required)

    Returns:
        Formatted transcript with basic metadata: title, author, duration, views, publish date, thumbnail, description
    """
    try:
        # Extract video ID if full URL provided
        video_id = youtube_service.get_video_id(video_id)

        # Check cache first
        cached = cache_service.get_cached_transcript(video_id)
        if cached:
            metadata = cached.get('metadata', {})
            basic_metadata = _extract_basic_metadata(metadata)
            return f"[CACHED] Title: {basic_metadata.get('title', 'Unknown')}\n" \
                   f"Author: {basic_metadata.get('author', 'Unknown')}\n" \
                   f"Duration: {basic_metadata.get('duration', 'N/A')}s\n" \
                   f"Views: {basic_metadata.get('view_count', 'N/A')}\n" \
                   f"Published: {basic_metadata.get('publish_date', 'N/A')}\n" \
                   f"Language: {cached.get('language', 'unknown')}\n" \
                   f"Thumbnail: {basic_metadata.get('thumbnail', 'N/A')}\n" \
                   f"Description: {basic_metadata.get('description', 'N/A')}\n\n" \
                   f"Transcript:\n{cached.get('transcript', '')}"

        # Fetch from YouTube (first available transcript)
        transcript_data = youtube_service.fetch_transcript(video_id)

        # Save to cache
        cache_service.save_transcript(video_id, transcript_data)

        metadata = transcript_data.get('metadata', {})
        basic_metadata = _extract_basic_metadata(metadata)

        return f"Title: {basic_metadata.get('title', 'Unknown')}\n" \
               f"Author: {basic_metadata.get('author', 'Unknown')}\n" \
               f"Duration: {basic_metadata.get('duration', 'N/A')}s\n" \
               f"Views: {basic_metadata.get('view_count', 'N/A')}\n" \
               f"Published: {basic_metadata.get('publish_date', 'N/A')}\n" \
               f"Language: {transcript_data.get('language', 'unknown')}\n" \
               f"Thumbnail: {basic_metadata.get('thumbnail', 'N/A')}\n" \
               f"Description: {basic_metadata.get('description', 'N/A')}\n\n" \
               f"Transcript:\n{transcript_data.get('transcript', '')}"

    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def clear_cache(video_id: str) -> str:
    """
    Clear cached transcript for a specific YouTube video.

    Args:
        video_id: YouTube video ID (11 characters) or full URL (required)

    Returns:
        Confirmation message with cache clearing status
    """
    try:
        # Extract video ID if full URL provided
        video_id = youtube_service.get_video_id(video_id)

        # Clear cache
        result = cache_service.clear_cache(video_id)

        if result['success']:
            return f"✓ {result['message']}"
        else:
            return f"✗ {result['message']}"

    except Exception as e:
        return f"Error: {str(e)}"


# Mount MCP server to FastAPI app (will be mounted in main.py)
def mount_mcp(app):
    """
    Mount MCP HTTP endpoint to FastAPI app at /api/v1/mcp.

    This endpoint supports StreamableHttpTransport for production use.
    Clients can connect using: StreamableHttpTransport(url="http://localhost:8000/api/v1/mcp")
    """
    _mcp_middleware = build_mcp_middleware_from_settings()

    mcp_http_app = mcp.http_app(
        path="/",
        stateless_http=True,
        middleware=_mcp_middleware,
    )

    app.mount("/api/v1/mcp", mcp_http_app)
