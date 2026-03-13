from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import tempfile
import threading

from app.config import settings


TERMINAL_JOB_STATES = {"completed", "failed"}
ACTIVE_JOB_STATES = {"queued", "downloading_audio", "extracting_audio", "loading_model", "uploading_audio", "awaiting_provider", "transcribing"}


class JobService:
    """File-backed background transcription status registry keyed by video_id."""

    def __init__(self, jobs_dir: Path | None = None):
        self.jobs_dir = jobs_dir or settings.APP_JOBS_DIR
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock_registry_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _get_job_file_path(self, video_id: str) -> Path:
        return self.jobs_dir / f"{video_id}.json"

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

    def _read_job_unlocked(self, path: Path) -> dict | None:
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_job(self, video_id: str) -> dict | None:
        path = self._get_job_file_path(video_id)
        with self._get_lock(video_id):
            return self._read_job_unlocked(path)

    def create_or_replace_job(self, *, video_id: str, backend: str, model: str) -> dict:
        now = datetime.now().isoformat()
        data = {
            "video_id": video_id,
            "backend": backend,
            "model": model,
            "status": "queued",
            "progress_percent": 0,
            "current_step": "queued",
            "message": "Transcription queued for this video_id",
            "created_at": now,
            "updated_at": now,
            "error": None,
            "result": None,
        }
        with self._get_lock(video_id):
            self._write_job(video_id, data)
        return data

    def update_job(self, video_id: str, **updates) -> dict:
        with self._get_lock(video_id):
            current = self._read_job_unlocked(self._get_job_file_path(video_id))
            if current is None:
                raise ValueError(f"Background transcription status for video {video_id} not found")

            current.update(updates)
            current["updated_at"] = datetime.now().isoformat()
            self._write_job(video_id, current)
            return current

    def mark_stale_jobs_failed(self) -> None:
        ttl = timedelta(days=settings.APP_JOB_POLL_TTL_DAYS)
        now = datetime.now()

        for path in self.jobs_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            status = data.get("status")
            updated_at_raw = data.get("updated_at") or data.get("created_at")
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except (TypeError, ValueError):
                updated_at = now

            if status in ACTIVE_JOB_STATES:
                data["status"] = "failed"
                data["current_step"] = "failed"
                data["message"] = "Background transcription interrupted by process restart"
                data["error"] = "interrupted"
                data["updated_at"] = now.isoformat()
                self._write_raw(path, data)
                continue

            if now - updated_at > ttl:
                path.unlink(missing_ok=True)

    def _write_job(self, video_id: str, data: dict) -> None:
        self._write_raw(self._get_job_file_path(video_id), data)

    def _write_raw(self, path: Path, data: dict) -> None:
        self._atomic_write_json(path, data)
