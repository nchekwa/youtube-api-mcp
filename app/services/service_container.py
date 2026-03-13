from dataclasses import dataclass
from functools import lru_cache


from app.services.background_transcription_service import BackgroundTranscriptionService
from app.services.cache_service import CacheService
from app.services.job_service import JobService
from app.services.transcript_from_audio_cache_service import TranscriptFromAudioCacheService
from app.services.youtube_service import YouTubeService


@dataclass(frozen=True)
class ServiceContainer:
    cache_service: CacheService
    transcript_from_audio_cache_service: TranscriptFromAudioCacheService
    youtube_service: YouTubeService
    job_service: JobService
    background_transcription_service: BackgroundTranscriptionService


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    cache_service = CacheService()
    transcript_from_audio_cache_service = TranscriptFromAudioCacheService(cache_service=cache_service)
    youtube_service = YouTubeService()
    job_service = JobService()
    background_transcription_service = BackgroundTranscriptionService(
        youtube_service=youtube_service,
        job_service=job_service,
        transcript_from_audio_cache_service=transcript_from_audio_cache_service,
    )
    return ServiceContainer(
        cache_service=cache_service,
        transcript_from_audio_cache_service=transcript_from_audio_cache_service,
        youtube_service=youtube_service,
        job_service=job_service,
        background_transcription_service=background_transcription_service,
    )
