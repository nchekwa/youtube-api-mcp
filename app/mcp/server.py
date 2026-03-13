from fastmcp import FastMCP

from app.config import settings
from app.services.service_container import get_service_container
from app.services.youtube_service import TranscriptFetchError
from app.utils.transcript_utils import build_audio_job_message, build_audio_transcript_payload, build_direct_transcript_payload, extract_basic_metadata


def _format_transcript_result(video_id: str, metadata: dict, direct_data: dict | None, audio_data: dict | None) -> str:
    basic_metadata = extract_basic_metadata(metadata)
    direct_payload = build_direct_transcript_payload(direct_data)
    audio_payload = build_audio_transcript_payload(audio_data)

    parts = [
        f"Video ID: {video_id}",
        f"Title: {basic_metadata.title}",
        f"Author: {basic_metadata.author}",
        f"Duration: {basic_metadata.duration}s",
        f"Views: {basic_metadata.view_count}",
        f"Published: {basic_metadata.publish_date}",
        f"Thumbnail: {basic_metadata.thumbnail or 'N/A'}",
        f"Description: {basic_metadata.description or 'N/A'}",
    ]

    if direct_payload:
        parts.extend([
            "",
            "[YOUTUBE TRANSCRIPT]",
            f"Language: {direct_payload.language}",
            f"Cache used: {direct_payload.cache_used}",
            direct_payload.transcript,
        ])

    if audio_payload:
        parts.extend([
            "",
            "[AUDIO TRANSCRIPT]",
            f"Language: {audio_payload.language}",
            f"Source: {audio_payload.source}",
            f"Cache used: {audio_payload.cache_used}",
            audio_payload.transcript,
        ])

    return "\n".join(parts)


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
        container = get_service_container()
        video_id = container.youtube_service.get_video_id(video_id)

        direct_data = container.cache_service.get_cached_transcript(video_id)
        if direct_data is None:
            direct_data = container.youtube_service.fetch_transcript(video_id)
            container.cache_service.save_transcript(video_id, direct_data)

        audio_data = container.transcript_from_audio_cache_service.get_cached_transcript(video_id)
        return _format_transcript_result(video_id, direct_data.get("metadata", {}), direct_data, audio_data)

    except TranscriptFetchError as e:
        if settings.APP_TRANSCRIPT_FROM_AUDIO and e.transcript_from_audio_allowed:
            container = get_service_container()
            transcript_from_audio_status = container.background_transcription_service.request_transcript(video_id)
            return build_audio_job_message(e.reason, transcript_from_audio_status)
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
        container = get_service_container()
        result = container.background_transcription_service.request_transcript(video_id)
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
        container = get_service_container()
        job = container.background_transcription_service.get_job_status(video_id)
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
        container = get_service_container()
        video_id = container.youtube_service.get_video_id(video_id)
        result = container.cache_service.clear_cache(video_id)

        if result['success']:
            return f"✓ {result['message']}"
        else:
            return f"✗ {result['message']}"

    except Exception as e:
        return f"Error: {str(e)}"


if not settings.APP_MCP_HIDE_CLEAR_CACHE:
    clear_cache = mcp.tool()(clear_cache)
