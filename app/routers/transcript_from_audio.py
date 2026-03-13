from fastapi import APIRouter, HTTPException, status, Depends

from app.middleware.auth import verify_api_key, API_KEYS
from app.models import BackgroundTranscriptJobResponse, BackgroundTranscriptRequestResponse
from app.services.background_transcription_service import BackgroundTranscriptionService


# Conditional dependencies - only add auth if API_KEYS is set
_router_dependencies = [Depends(verify_api_key)] if API_KEYS else []

router = APIRouter(
    prefix="/youtube/audio-transcript",
    tags=["youtube"],
    dependencies=_router_dependencies,
)
background_transcription_service = BackgroundTranscriptionService()


@router.post("/{video_id:path}", response_model=BackgroundTranscriptRequestResponse, summary="Queue Audio Transcription By Video ID")
async def request_audio_transcript(video_id: str):
    """
    Queue or reuse transcript_from_audio processing tracked by video_id.
    """
    try:
        data = background_transcription_service.request_transcript(video_id)
        return BackgroundTranscriptRequestResponse(**data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error queueing audio transcript job: {str(e)}",
        )


@router.get("/{video_id}", response_model=BackgroundTranscriptJobResponse, summary="Get Audio Transcription Status")
async def get_audio_transcript(video_id: str):
    """
    Get the current status of a background audio transcription process by video ID.
    """
    job = background_transcription_service.get_job_status(video_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No background transcription status found for video {video_id}",
        )

    return BackgroundTranscriptJobResponse(**job)
