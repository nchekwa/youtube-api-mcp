from fastapi import APIRouter, HTTPException, status, Query, Depends
from app.config import settings
from app.models import TranscriptResponse, TranscriptFromAudioResponse
from app.services.cache_service import CacheService
from app.services.background_transcription_service import BackgroundTranscriptionService
from app.services.transcript_from_audio_cache_service import TranscriptFromAudioCacheService
from app.services.youtube_service import YouTubeService
from app.services.youtube_service import TranscriptFetchError
from app.middleware.auth import verify_api_key, API_KEYS
from slowapi import Limiter


def _extract_basic_metadata(metadata: dict) -> dict:
    """Extract basic fields from full metadata."""
    return {
        "title": metadata.get("title", "Unknown"),
        "author": metadata.get("author", "Unknown"),
        "duration": metadata.get("duration", 0),
        "publish_date": metadata.get("upload_date", "Unknown"),
        "view_count": metadata.get("view_count", 0),
        "thumbnail": metadata.get("thumbnail"),  # Can be None
        "description": metadata.get("description")  # Can be None
    }

# Conditional dependencies - only add auth if API_KEYS is set
_router_dependencies = [Depends(verify_api_key)] if API_KEYS else []

router = APIRouter(
    prefix="/youtube/transcript",
    tags=["youtube"],
    dependencies=_router_dependencies
)
cache_service = CacheService()
transcript_from_audio_cache_service = TranscriptFromAudioCacheService()
youtube_service = YouTubeService()
background_transcription_service = BackgroundTranscriptionService()


def _build_transcript_from_audio_message(reason: str, transcript_from_audio_status: dict) -> str:
    status = transcript_from_audio_status.get("status", "queued")
    video_id = transcript_from_audio_status.get("video_id", "unknown")
    background_message = transcript_from_audio_status.get("message", "Background audio transcription was queued.")
    suffix = "The transcript should be available in a few minutes." if status != "completed" else "A transcript_from_audio result is already available."
    return (
        f"Direct YouTube transcript fetch failed: {reason}. "
        f"Transcript_from_audio status for video_id {video_id} is '{status}'. "
        f"Background transcription message: {background_message}. "
        f"{suffix} Check status by the same video_id."
    )


def _merge_direct_and_audio_transcripts(direct_transcript: str, audio_cached: dict | None) -> str:
    if not audio_cached or not audio_cached.get("transcript"):
        return direct_transcript

    return f"{direct_transcript}\n\n[TRANSCRIPT FROM AUDIO TRACK]\n{audio_cached.get('transcript', '')}"


# IMPORTANT: /raw endpoint must be defined BEFORE /{video_id:path} endpoint
# Otherwise FastAPI will match "raw/qrxI6gBn3YE" as video_id for the first endpoint
@router.get("/raw/{video_id:path}", response_model=dict, summary="Get Full YouTube Metadata")
async def get_transcript_raw(
    video_id: str,
    use_cache: bool = Query(default=True, description="Use cached data if available")
):
    """
    Fetches transcript with **complete yt-dlp metadata** for a YouTube video.

    **Features:**
    - Extracts video ID from full URL or accepts 11-character ID
    - Always returns first available transcript (native/original language)
    - Caches results locally (30 days TTL)
    - Returns **full metadata** with all yt-dlp fields

    **Parameters:**
    - `video_id`: YouTube video ID (11 chars) or full URL (goes after /raw/)
    - `use_cache`: Enable/disable cache (default: true)

    **Example:**
    - `/api/v1/youtube/transcript/raw/mQ-y2ZOTpr4`
    - `/api/v1/youtube/transcript/raw/https://www.youtube.com/watch?v=mQ-y2ZOTpr4`

    **Returns:**
    - `video_id`: Unique YouTube identifier
    - `transcript`: Full transcript text (first available language)
    - `metadata`: Complete yt-dlp metadata (50+ fields including:
      - Basic: title, author, duration, views, upload date
      - Engagement: likes, comments
      - Media: description, thumbnails, categories, tags
      - Technical: resolution, codecs, format, filesize
      - Channel: channel_id, followers, location
      - Subtitles: available and auto-generated captions)
    - `language`: Language code of the returned transcript
    - `cache_used`: Whether response came from cache (true) or was fetched fresh (false)
    - `cached_at`: ISO timestamp when cached (null if cache_used=false)
    """
    try:
        # Extract video ID if full URL provided
        video_id = youtube_service.get_video_id(video_id)

        # Check cache first if enabled
        if use_cache:
            cached = cache_service.get_cached_transcript(video_id)
            if cached:
                audio_cached = transcript_from_audio_cache_service.get_cached_transcript(video_id)
                return {
                    "video_id": video_id,
                    "transcript": _merge_direct_and_audio_transcripts(cached.get("transcript", ""), audio_cached),
                    "language": cached.get("language", "unknown"),
                    "cache_used": True,
                    "cached_at": cached.get("cached_at"),
                    "metadata": cached.get("metadata", {})
                }

        # Fetch from YouTube (first available transcript)
        transcript_data = youtube_service.fetch_transcript(video_id)

        # Save to cache
        if use_cache:
            cache_service.save_transcript(video_id, transcript_data)

        return {
            "video_id": video_id,
            "transcript": transcript_data.get("transcript", ""),
            "language": transcript_data.get("language", "unknown"),
            "cache_used": False,
            "cached_at": None,
            "metadata": transcript_data.get("metadata", {})
        }

    except TranscriptFetchError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.reason
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching transcript: {str(e)}"
        )


@router.get("/{video_id:path}", response_model=TranscriptResponse | TranscriptFromAudioResponse, summary="Get YouTube Video Transcript")
async def get_transcript(
    video_id: str,
    use_cache: bool = Query(default=True, description="Use cached data if available")
):
    """
    Fetches transcript with basic metadata for a YouTube video.

    **Features:**
    - Extracts video ID from full URL or accepts 11-character ID
    - Always returns first available transcript (native/original language)
    - Caches results locally (30 days TTL)
    - Returns basic metadata: title, author, duration, views, publish date, thumbnail, description
    - Can auto-queue `transcript_from_audio` processing when direct YouTube transcript fetch fails and `_APP_TRANSCRIPT_FROM_AUDIO=true`

    **Parameters:**
    - `video_id`: YouTube video ID (11 chars) or full URL
    - `use_cache`: Enable/disable cache (default: true)

    **Example:**
    - `/api/v1/youtube/transcript/mQ-y2ZOTpr4`
    - `/api/v1/youtube/transcript/https://www.youtube.com/watch?v=mQ-y2ZOTpr4`

    **Returns:**
    - `video_id`: Unique YouTube identifier
    - `transcript`: Full transcript text (first available language), when direct YouTube transcript fetch succeeds
    - `metadata`: Basic video info including:
      - `title`: Video title
      - `author`: Channel/author name
      - `duration`: Video duration in seconds
      - `publish_date`: Upload date (YYYY-MM-DD)
      - `view_count`: Number of views
      - `thumbnail`: URL to video thumbnail (can be null)
      - `description`: Video description (can be null)
    - `language`: Language code of the returned transcript
    - `cache_used`: Whether response came from cache (true) or was fetched fresh (false)
    - `cached_at`: ISO timestamp when cached (null if cache_used=false)
    """
    try:
        # Extract video ID if full URL provided
        video_id = youtube_service.get_video_id(video_id)

        # Check cache first if enabled
        if use_cache:
            cached = cache_service.get_cached_transcript(video_id)
            if cached:
                audio_cached = transcript_from_audio_cache_service.get_cached_transcript(video_id)
                # Extract basic metadata from full metadata in cache
                cached["metadata"] = _extract_basic_metadata(cached["metadata"])
                cached["transcript"] = _merge_direct_and_audio_transcripts(cached.get("transcript", ""), audio_cached)
                return TranscriptResponse(**cached)

        # Fetch from YouTube (first available transcript)
        transcript_data = youtube_service.fetch_transcript(video_id)

        # Save to cache
        if use_cache:
            cache_service.save_transcript(video_id, transcript_data)

        # Extract basic metadata for response (cache has full metadata)
        transcript_data["metadata"] = _extract_basic_metadata(transcript_data["metadata"])
        transcript_data["cache_used"] = False

        if use_cache:
            audio_cached = transcript_from_audio_cache_service.get_cached_transcript(video_id)
            transcript_data["transcript"] = _merge_direct_and_audio_transcripts(transcript_data.get("transcript", ""), audio_cached)

        return TranscriptResponse(**transcript_data)

    except TranscriptFetchError as e:
        if settings.APP_TRANSCRIPT_FROM_AUDIO and e.transcript_from_audio_allowed:
            transcript_from_audio_status = background_transcription_service.request_transcript(video_id)
            return TranscriptFromAudioResponse(
                video_id=video_id,
                status=transcript_from_audio_status.get("status", "queued"),
                message=_build_transcript_from_audio_message(e.reason, transcript_from_audio_status),
                progress_percent=transcript_from_audio_status.get("progress_percent", 0),
                transcript_from_audio_reason=e.reason,
                result=transcript_from_audio_status.get("result"),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.reason
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching transcript: {str(e)}"
        )
