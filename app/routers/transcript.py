from fastapi import APIRouter, HTTPException, Request, status, Query, Depends

from app.config import settings
from app.middleware.auth import API_KEYS, verify_api_key
from app.models import RawTranscriptResponse, TranscriptRequestAcceptedResponse, TranscriptResponse
from app.rate_limiter import limiter
from app.services.service_container import ServiceContainer, get_service_container
from app.services.youtube_service import TranscriptFetchError
from app.utils.transcript_utils import build_audio_job_message, build_audio_transcript_payload, build_direct_transcript_payload, extract_basic_metadata

# Conditional dependencies - only add auth if API_KEYS is set
_router_dependencies = [Depends(verify_api_key)] if API_KEYS else []

router = APIRouter(
    prefix="/youtube/transcript",
    tags=["youtube"],
    dependencies=_router_dependencies,
)


# IMPORTANT: /raw endpoint must be defined BEFORE /{video_id:path} endpoint
# Otherwise FastAPI will match "raw/qrxI6gBn3YE" as video_id for the first endpoint
@router.get("/raw/{video_id:path}", response_model=RawTranscriptResponse, summary="Get Full YouTube Metadata")
@limiter.limit("30/minute")
async def get_transcript_raw(
    request: Request,
    video_id: str,
    use_cache: bool = Query(default=settings.APP_USE_CACHE_DEFAULT, description="Use cached data if available"),
    force_refresh: bool = Query(default=False, description="Fetch fresh data and overwrite direct transcript cache"),
    language: str | None = Query(default=None, description="Preferred transcript language code"),
    container: ServiceContainer = Depends(get_service_container),
):
    try:
        del request
        video_id = container.youtube_service.get_video_id(video_id)
        preferred_languages = [language] if language else []

        direct_payload = None
        cached_direct = None
        if use_cache and not force_refresh:
            cached_direct = container.cache_service.get_cached_transcript(video_id)
            direct_payload = build_direct_transcript_payload(cached_direct)

        if direct_payload is None:
            transcript_data = await container.youtube_service.fetch_transcript_async(video_id, preferred_languages)
            if use_cache or force_refresh:
                container.cache_service.save_transcript(video_id, transcript_data)
            cached_direct = transcript_data
            direct_payload = build_direct_transcript_payload(transcript_data)

        audio_cached = container.transcript_from_audio_cache_service.get_cached_transcript(video_id)
        return RawTranscriptResponse(
            video_id=video_id,
            metadata=cached_direct.get("metadata", {}) if cached_direct else {},
            transcript_youtube=direct_payload,
            transcript_audio=build_audio_transcript_payload(audio_cached),
            source_preference=["youtube", "audio"],
        )

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


@router.get("/{video_id:path}", response_model=TranscriptResponse | TranscriptRequestAcceptedResponse, summary="Get YouTube Video Transcript")
@limiter.limit("30/minute")
async def get_transcript(
    request: Request,
    video_id: str,
    use_cache: bool = Query(default=settings.APP_USE_CACHE_DEFAULT, description="Use cached data if available"),
    force_refresh: bool = Query(default=False, description="Fetch fresh data and overwrite direct transcript cache"),
    language: str | None = Query(default=None, description="Preferred transcript language code"),
    container: ServiceContainer = Depends(get_service_container),
):
    try:
        del request
        video_id = container.youtube_service.get_video_id(video_id)
        preferred_languages = [language] if language else []

        direct_data = None
        if use_cache and not force_refresh:
            direct_data = container.cache_service.get_cached_transcript(video_id)

        if direct_data is None:
            direct_data = await container.youtube_service.fetch_transcript_async(video_id, preferred_languages)
            if use_cache or force_refresh:
                container.cache_service.save_transcript(video_id, direct_data)

        audio_cached = container.transcript_from_audio_cache_service.get_cached_transcript(video_id)
        return TranscriptResponse(
            video_id=video_id,
            metadata=extract_basic_metadata(direct_data.get("metadata", {})),
            transcript_youtube=build_direct_transcript_payload(direct_data),
            transcript_audio=build_audio_transcript_payload(audio_cached),
            source_preference=["youtube", "audio"],
        )

    except TranscriptFetchError as e:
        if settings.APP_TRANSCRIPT_FROM_AUDIO and e.transcript_from_audio_allowed:
            transcript_from_audio_status = container.background_transcription_service.request_transcript(video_id)
            return TranscriptRequestAcceptedResponse(
                video_id=video_id,
                status=transcript_from_audio_status.get("status", "queued"),
                message=build_audio_job_message(e.reason, transcript_from_audio_status),
                progress_percent=transcript_from_audio_status.get("progress_percent", 0),
                transcript_from_audio_reason=e.reason,
                result=build_audio_transcript_payload(transcript_from_audio_status.get("result")),
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
