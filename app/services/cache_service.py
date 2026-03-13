from pathlib import Path
from datetime import datetime, timedelta
import json
import logging
import os
import threading
import tempfile
from app.config import settings


logger = logging.getLogger("uvicorn.error")


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
        self._lock_registry_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _iter_cache_files(self) -> list[Path]:
        if not self.cache_dir.exists():
            return []
        return sorted(
            (path for path in self.cache_dir.glob("*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
        )

    def get_cache_size(self) -> int:
        """
        Get the number of cached transcript files.

        Returns:
            Number of JSON files in cache directory
        """
        if not self.cache_dir.exists():
            return 0
        return len(self._iter_cache_files())

    def get_cache_size_bytes(self) -> int:
        return sum(path.stat().st_size for path in self._iter_cache_files())

    def get_cache_size_mb(self) -> float:
        return round(self.get_cache_size_bytes() / (1024 * 1024), 3)

    def list_cache_entries(self) -> list[dict]:
        entries: list[dict] = []
        for path in self._iter_cache_files():
            entries.append(
                {
                    "video_id": path.stem,
                    "file_name": path.name,
                    "size_bytes": path.stat().st_size,
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
            )
        return entries

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

    def _get_lock(self, video_id: str) -> threading.Lock:
        with self._lock_registry_guard:
            lock = self._locks.get(video_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[video_id] = lock
            return lock

    def _atomic_write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp_file:
            json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, path)

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
        self._atomic_write_json(cache_file, payload)
        self._enforce_cache_size_limit(exclude_video_id=video_id)

    def _enforce_cache_size_limit(self, exclude_video_id: str | None = None) -> None:
        max_bytes = max(0, settings.APP_MAX_CACHE_SIZE_MB) * 1024 * 1024
        if max_bytes <= 0:
            return

        current_size = self.get_cache_size_bytes()
        if current_size <= max_bytes:
            return

        for cache_file in self._iter_cache_files():
            if exclude_video_id and cache_file.stem == exclude_video_id:
                continue

            lock = self._get_lock(cache_file.stem)
            with lock:
                file_size = cache_file.stat().st_size if cache_file.exists() else 0
                cache_file.unlink(missing_ok=True)
                current_size = max(0, current_size - file_size)
                logger.warning("Evicted cache entry %s to enforce APP_MAX_CACHE_SIZE_MB", cache_file.name)

            if current_size <= max_bytes:
                return

        if current_size > max_bytes and exclude_video_id:
            logger.warning(
                "Cache size remains above APP_MAX_CACHE_SIZE_MB after eviction because only protected entry %s remains",
                exclude_video_id,
            )

    def _delete_cache_file_if_empty(self, video_id: str, payload: dict) -> None:
        if payload.get(self.DIRECT_SECTION) or payload.get(self.AUDIO_SECTION):
            self._write_cache_payload(video_id, payload)
            return

        self._get_cache_file_path(video_id).unlink(missing_ok=True)

    def _get_section(self, video_id: str, section_name: str) -> dict | None:
        with self._get_lock(video_id):
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

            ttl_days = settings.APP_CACHE_TTL_DAYS
            if ttl_days > 0 and datetime.now() - cached_at > timedelta(days=ttl_days):
                payload.pop(section_name, None)
                self._delete_cache_file_if_empty(video_id, payload)
                return None

            return dict(section)

    def _save_section(self, video_id: str, section_name: str, data: dict) -> None:
        with self._get_lock(video_id):
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

    def clear_all_cache(self) -> dict:
        deleted_entries = 0
        for cache_file in self._iter_cache_files():
            with self._get_lock(cache_file.stem):
                if cache_file.exists():
                    cache_file.unlink(missing_ok=True)
                    deleted_entries += 1

        return {
            "success": True,
            "message": f"Cleared {deleted_entries} cache entries",
            "deleted_entries": deleted_entries,
        }

    def clear_cache(self, video_id: str) -> dict:
        """
        Clear cached transcript files for a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with status and message
        """
        cache_file = self._get_cache_file_path(video_id)
        with self._get_lock(video_id):
            if not cache_file.exists():
                return {
                    "success": False,
                    "message": f"No cache found for video {video_id}"
                }

            try:
                cache_file.unlink(missing_ok=True)
                return {
                    "success": True,
                    "message": f"Cache cleared for video {video_id}: {cache_file.name}",
                    "deleted_entries": 1,
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error clearing cache: {str(e)}",
                    "deleted_entries": 0,
                }
