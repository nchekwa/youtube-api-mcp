from pathlib import Path

from app.services.cache_service import CacheService


class TranscriptFromAudioCacheService:
    """Service for managing transcript_from_audio cache access."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_service = CacheService(cache_dir=cache_dir)

    def get_cached_transcript(self, video_id: str) -> dict | None:
        return self.cache_service.get_cached_audio_transcript(video_id)

    def save_transcript(self, video_id: str, data: dict) -> None:
        self.cache_service.save_audio_transcript(video_id, data)
