from pathlib import Path
from datetime import datetime, timedelta
import json
from app.config import settings


class CacheService:
    """Service for managing transcript cache files."""

    DIRECT_SECTION = "direct_from_youtube"
    AUDIO_SECTION = "transcript_from_audio"

    def __init__(self, cache_dir: Path | None = None):
        """
        Initialize cache service.

        Args:
            cache_dir: Optional custom cache directory. Defaults to settings.APP_CACHE_DIR
        """
        self.cache_dir = cache_dir or settings.APP_CACHE_DIR
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_size(self) -> int:
        """
        Get the number of cached transcript files.

        Returns:
            Number of JSON files in cache directory
        """
        if not self.cache_dir.exists():
            return 0
        return len(list(self.cache_dir.glob("*.json")))

    def _get_cache_file_path(self, video_id: str) -> Path:
        """
        Generate cache file path for a video.

        Args:
            video_id: YouTube video ID

        Returns:
            Path to cache file
        """
        filename = f"{video_id}.json"
        return self.cache_dir / filename

    def _read_cache_payload(self, video_id: str) -> dict | None:
        cache_file = self._get_cache_file_path(video_id)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError, KeyError):
            cache_file.unlink(missing_ok=True)
            return None

        if not isinstance(data, dict):
            cache_file.unlink(missing_ok=True)
            return None

        return data

    def _write_cache_payload(self, video_id: str, payload: dict) -> None:
        cache_file = self._get_cache_file_path(video_id)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _delete_cache_file_if_empty(self, video_id: str, payload: dict) -> None:
        if payload.get(self.DIRECT_SECTION) or payload.get(self.AUDIO_SECTION):
            self._write_cache_payload(video_id, payload)
            return

        self._get_cache_file_path(video_id).unlink(missing_ok=True)

    def _get_section(self, video_id: str, section_name: str) -> dict | None:
        payload = self._read_cache_payload(video_id)
        if not payload:
            return None

        section = payload.get(section_name)
        if not isinstance(section, dict):
            if section_name in payload:
                payload.pop(section_name, None)
                self._delete_cache_file_if_empty(video_id, payload)
            return None

        try:
            cached_at = datetime.fromisoformat(section.get('cached_at', ''))
        except (TypeError, ValueError):
            payload.pop(section_name, None)
            self._delete_cache_file_if_empty(video_id, payload)
            return None

        max_age = timedelta(days=settings.APP_CACHE_TTL_DAYS)
        if datetime.now() - cached_at > max_age:
            payload.pop(section_name, None)
            self._delete_cache_file_if_empty(video_id, payload)
            return None

        return dict(section)

    def _save_section(self, video_id: str, section_name: str, data: dict) -> None:
        payload = self._read_cache_payload(video_id) or {"video_id": video_id}
        section_payload = dict(data)
        section_payload['cached_at'] = datetime.now().isoformat()
        section_payload['cache_used'] = True
        payload['video_id'] = video_id
        payload[section_name] = section_payload
        self._write_cache_payload(video_id, payload)

    def get_cached_transcript(self, video_id: str) -> dict | None:
        """
        Get transcript from cache if available and not expired.

        Args:
            video_id: YouTube video ID

        Returns:
            Cached transcript dict or None if not found/expired
        """
        return self._get_section(video_id, self.DIRECT_SECTION)

    def get_cached_audio_transcript(self, video_id: str) -> dict | None:
        return self._get_section(video_id, self.AUDIO_SECTION)

    def save_transcript(self, video_id: str, data: dict) -> None:
        """
        Save transcript to cache.

        Args:
            video_id: YouTube video ID
            data: Transcript data to cache
        """
        self._save_section(video_id, self.DIRECT_SECTION, data)

    def save_audio_transcript(self, video_id: str, data: dict) -> None:
        self._save_section(video_id, self.AUDIO_SECTION, data)

    def clear_cache(self, video_id: str) -> dict:
        """
        Clear cached transcript files for a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with status and message
        """
        cache_file = self._get_cache_file_path(video_id)
        if not cache_file.exists():
            return {
                "success": False,
                "message": f"No cache found for video {video_id}"
            }

        try:
            cache_file.unlink(missing_ok=True)
            return {
                "success": True,
                "message": f"Cache cleared for video {video_id}: {cache_file.name}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error clearing cache: {str(e)}"
            }
