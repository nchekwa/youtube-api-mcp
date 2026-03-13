from fastmcp import FastMCP
from app.config import settings
from starlette.middleware import Middleware
from app.middleware.auth import MCPAPIKeyMiddleware, build_mcp_middleware_from_settings
from app.services.background_transcription_service import BackgroundTranscriptionService
from app.services.youtube_service import YouTubeService
from app.services.youtube_service import TranscriptFetchError
from app.services.cache_service import CacheService
from app.services.transcript_from_audio_cache_service import TranscriptFromAudioCacheService

# Initialize services
youtube_service = YouTubeService()
cache_service = CacheService()
transcript_from_audio_cache_service = TranscriptFromAudioCacheService()
background_transcription_service = BackgroundTranscriptionService()


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


def _build_transcript_from_audio_message(reason: str, transcript_from_audio_status: dict) -> str:
    status = transcript_from_audio_status.get("status", "queued")
    video_id = transcript_from_audio_status.get("video_id", "unknown")
    background_message = transcript_from_audio_status.get("message", "Background transcript_from_audio processing was queued.")
    suffix = "The transcript should be available in a few minutes." if status != "completed" else "A transcript_from_audio result is already available."
    return (
        f"Direct YouTube transcript fetch failed: {reason}.\n"
        f"Transcript_from_audio status for video_id {video_id}: {status}.\n"
        f"Background transcription message: {background_message}.\n"
        f"Progress: {transcript_from_audio_status.get('progress_percent', 0)}%\n"
        f"{suffix}\n"
        f"Check status by the same video_id."
    )


def _merge_direct_and_audio_transcripts(direct_transcript: str, audio_cached: dict | None) -> str:
    if not audio_cached or not audio_cached.get("transcript"):
        return direct_transcript

    return f"{direct_transcript}\n\n[TRANSCRIPT FROM AUDIO TRACK]\n{audio_cached.get('transcript', '')}"


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
            audio_cached = transcript_from_audio_cache_service.get_cached_transcript(video_id)
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
                   f"Transcript:\n{_merge_direct_and_audio_transcripts(cached.get('transcript', ''), audio_cached)}"

        # Fetch from YouTube (first available transcript)
        transcript_data = youtube_service.fetch_transcript(video_id)

        # Save to cache
        cache_service.save_transcript(video_id, transcript_data)

        audio_cached = transcript_from_audio_cache_service.get_cached_transcript(video_id)
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
               f"Transcript:\n{_merge_direct_and_audio_transcripts(transcript_data.get('transcript', ''), audio_cached)}"

    except TranscriptFetchError as e:
        if settings.APP_TRANSCRIPT_FROM_AUDIO and e.transcript_from_audio_allowed:
            transcript_from_audio_status = background_transcription_service.request_transcript(video_id)
            return _build_transcript_from_audio_message(e.reason, transcript_from_audio_status)
        return f"Error: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def request_youtube_audio_transcript(video_id: str) -> str:
    """
    Queue background transcription for a YouTube video tracked by video_id.

    Args:
        video_id: YouTube video ID (11 characters) or full URL (required)

    Returns:
        Current background transcription status or completed transcript_from_audio result
    """
    try:
        result = background_transcription_service.request_transcript(video_id)
        if result.get("result"):
            transcript_result = result["result"]
            metadata = transcript_result.get("metadata", {})
            return f"Status: completed\n" \
                   f"Video ID: {transcript_result.get('video_id')}\n" \
                   f"Source: {transcript_result.get('source', 'local_whisper')}\n" \
                   f"Language: {transcript_result.get('language', 'unknown')}\n" \
                   f"Title: {metadata.get('title', 'Unknown')}\n" \
                   f"Author: {metadata.get('author', 'Unknown')}\n" \
                   f"Transcript:\n{transcript_result.get('transcript', '')}"

        return f"Status: {result.get('status', 'queued')}\n" \
               f"Video ID: {result.get('video_id', 'N/A')}\n" \
               f"Progress: {result.get('progress_percent', 0)}%\n" \
               f"Message: {result.get('message', 'Queued')}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_youtube_audio_transcript(video_id: str) -> str:
    """
    Check the status of a background YouTube audio transcription process by video ID.

    Args:
        video_id: YouTube video ID (11 characters) or full URL (required)

    Returns:
        Detailed background transcription status, including transcript once completed
    """
    try:
        job = background_transcription_service.get_job_status(video_id)
        if not job:
            return f"Error: No background transcription status found for video {video_id}"

        result = job.get("result") or {}
        transcript = result.get("transcript")
        response = f"Status: {job.get('status', 'unknown')}\n" \
                   f"Video ID: {job.get('video_id', 'N/A')}\n" \
                   f"Step: {job.get('current_step', 'unknown')}\n" \
                   f"Progress: {job.get('progress_percent', 0)}%\n" \
                   f"Message: {job.get('message', '')}"

        if job.get("error"):
            response += f"\nError: {job.get('error')}"

        if transcript:
            response += f"\n\nTranscript:\n{transcript}"

        return response
    except Exception as e:
        return f"Error: {str(e)}"


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


if not settings.APP_MCP_HIDE_CLEAR_CACHE:
    clear_cache = mcp.tool()(clear_cache)


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
