from pathlib import Path
from datetime import datetime, timedelta
import json
from app.config import settings


class CacheService:
    """Service for managing transcript cache files."""

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

    def _get_cache_file_path(self, video_id: str, language: str = "pl") -> Path:
        """
        Generate cache file path for a video.

        Args:
            video_id: YouTube video ID
            language: Language code

        Returns:
            Path to cache file
        """
        filename = f"{video_id}_{language}.json"
        return self.cache_dir / filename

    def get_cached_transcript(self, video_id: str, language: str = "pl") -> dict | None:
        """
        Get transcript from cache if available and not expired.

        Args:
            video_id: YouTube video ID
            language: Language code

        Returns:
            Cached transcript dict or None if not found/expired
        """
        cache_file = self._get_cache_file_path(video_id, language)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check if cache is expired
            cached_at = datetime.fromisoformat(data.get('cached_at', ''))
            max_age = timedelta(days=settings.APP_CACHE_TTL_DAYS)

            if datetime.now() - cached_at > max_age:
                # Cache expired, delete file
                cache_file.unlink()
                return None

            return data
        except (json.JSONDecodeError, ValueError, KeyError):
            # Invalid cache file, delete it
            cache_file.unlink(missing_ok=True)
            return None

    def save_transcript(self, video_id: str, data: dict, language: str = "pl") -> None:
        """
        Save transcript to cache.

        Args:
            video_id: YouTube video ID
            data: Transcript data to cache
            language: Language code
        """
        cache_file = self._get_cache_file_path(video_id, language)

        # Add cache metadata
        data['cached_at'] = datetime.now().isoformat()
        data['cache_used'] = True  # Mark as coming from cache when loaded

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear_cache(self, video_id: str, language: str = "en") -> dict:
        """
        Clear cached transcript for a specific video.

        Args:
            video_id: YouTube video ID
            language: Language code

        Returns:
            Dict with status and message
        """
        cache_file = self._get_cache_file_path(video_id, language)

        if not cache_file.exists():
            return {
                "success": False,
                "message": f"No cache found for video {video_id} (language: {language})"
            }

        try:
            cache_file.unlink()
            return {
                "success": True,
                "message": f"Cache cleared for video {video_id} (language: {language})"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error clearing cache: {str(e)}"
            }
