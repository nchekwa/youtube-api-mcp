from __future__ import annotations

from pathlib import Path
import logging
import shutil
import subprocess
import threading

from app.config import settings
from app.utils.transcript_utils import extract_basic_metadata
from app.services.transcript_from_audio_cache_service import TranscriptFromAudioCacheService
from app.services.job_service import ACTIVE_JOB_STATES, JobService
from app.services.transcription_backend_service import TranscriptionBackendService
from app.services.youtube_service import YouTubeService

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False


logger = logging.getLogger("uvicorn.error")


class BackgroundTranscriptionService:
    """Coordinates background audio download, extraction, and local transcription."""

    def __init__(
        self,
        youtube_service: YouTubeService | None = None,
        job_service: JobService | None = None,
        transcript_from_audio_cache_service: TranscriptFromAudioCacheService | None = None,
    ):
        self.youtube_service = youtube_service or YouTubeService()
        self.job_service = job_service or JobService()
        self.transcript_from_audio_cache_service = transcript_from_audio_cache_service or TranscriptFromAudioCacheService()
        self.work_dir = settings.APP_WORK_DIR
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = threading.Semaphore(max(1, settings.APP_BACKGROUND_JOB_CONCURRENCY))
        self._lock = threading.Lock()
        self._running_jobs: set[str] = set()
        self._model = None
        self.transcription_backend_service = TranscriptionBackendService(
            update_job_status=self._update_job_status,
            get_local_model=self._get_model,
        )
        self.job_service.mark_stale_jobs_failed()

    def request_transcript(self, url_or_id: str) -> dict:
        self.job_service.mark_stale_jobs_failed()
        video_id = self.youtube_service.get_video_id(url_or_id)
        backend = self.transcription_backend_service.get_backend_name()
        backend_model = self.transcription_backend_service.get_backend_model_key()

        cached = self.transcript_from_audio_cache_service.get_cached_transcript(video_id)
        if cached:
            cached["cache_used"] = True
            return {
                "status": "completed",
                "video_id": video_id,
                "message": f"Transcript already exists in cache/{video_id}.json under transcript_from_audio",
                "progress_percent": 100,
                "result": cached,
            }

        current_job = self.job_service.get_job(video_id)

        if current_job and current_job.get("status") in ACTIVE_JOB_STATES:
            return {
                "status": current_job["status"],
                "video_id": video_id,
                "message": current_job.get("message", "Transcription already in progress for this video_id"),
                "progress_percent": current_job.get("progress_percent", 0),
                "result": current_job.get("result"),
            }

        if current_job and current_job.get("status") == "completed" and current_job.get("result"):
            return {
                "status": "completed",
                "video_id": video_id,
                "message": current_job.get("message", "Transcript already prepared"),
                "progress_percent": 100,
                "result": current_job.get("result"),
            }

        self.job_service.create_or_replace_job(video_id=video_id, backend=backend, model=backend_model)
        logger.info("[%s] Background transcription entry created for backend=%s model=%s", video_id, backend, backend_model)
        self._ensure_job_started(video_id)

        return {
            "status": "queued",
            "video_id": video_id,
            "message": f"Transcript queued for background processing by video_id using backend '{backend}'",
            "progress_percent": 0,
            "result": None,
        }

    def get_job_status(self, video_id: str) -> dict | None:
        self.job_service.mark_stale_jobs_failed()
        normalized_video_id = self.youtube_service.get_video_id(video_id)
        return self.job_service.get_job(normalized_video_id)

    def is_model_loaded(self) -> bool:
        return self._model is not None

    def _ensure_job_started(self, video_id: str) -> None:
        with self._lock:
            if video_id in self._running_jobs:
                logger.info("[%s] Worker already running", video_id)
                return
            self._running_jobs.add(video_id)

        logger.info("[%s] Starting background worker", video_id)
        worker = threading.Thread(
            target=self._run_job,
            args=(video_id,),
            daemon=True,
        )
        worker.start()

    def _run_job(self, video_id: str) -> None:
        try:
            logger.info("[%s] Background worker entered run loop", video_id)
            with self._semaphore:
                logger.info("[%s] Background worker acquired execution slot", video_id)
                self._process_job(video_id)
        except Exception as e:
            logger.exception("[%s] Background worker crashed: %s", video_id, str(e))
            self.job_service.update_job(
                video_id,
                status="failed",
                current_step="failed",
                progress_percent=100,
                message="Background transcription failed",
                error=str(e),
            )
        finally:
            with self._lock:
                self._running_jobs.discard(video_id)
            logger.info("[%s] Background worker finished", video_id)

    def _process_job(self, video_id: str) -> None:
        if not YTDLP_AVAILABLE:
            raise RuntimeError("yt-dlp is not installed")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is not installed or not available in PATH")

        backend = self.transcription_backend_service.get_backend_name()
        if backend == "faster-whisper" and not FASTER_WHISPER_AVAILABLE:
            raise RuntimeError("faster-whisper is not installed")

        job_dir = self.work_dir / video_id
        job_dir.mkdir(parents=True, exist_ok=True)
        audio_source = job_dir / "source_audio"
        normalized_wav = job_dir / "audio.wav"
        logger.info("[%s] Using work directory: %s (backend=%s)", video_id, job_dir, backend)

        try:
            self._update_job_status(
                video_id,
                status="downloading_audio",
                current_step="downloading_audio",
                progress_percent=10,
                message=f"Downloading source audio from YouTube into {job_dir} for backend '{backend}'",
            )
            metadata = self.youtube_service.get_video_metadata(video_id)
            downloaded_audio = self._download_audio(video_id, audio_source)
            logger.info("[%s] Downloaded audio file: %s", video_id, downloaded_audio)

            self._update_job_status(
                video_id,
                status="extracting_audio",
                current_step="extracting_audio",
                progress_percent=45,
                message=f"Normalizing audio from {downloaded_audio} to {normalized_wav}",
            )
            self._extract_audio(downloaded_audio, normalized_wav)
            logger.info("[%s] Normalized WAV file ready: %s", video_id, normalized_wav)

            self._update_job_status(
                video_id,
                status="loading_model",
                current_step="loading_model",
                progress_percent=60,
                message=f"Preparing transcription backend '{backend}' for {normalized_wav}",
            )
            if backend == "faster-whisper":
                self._get_model(video_id)

            self._update_job_status(
                video_id,
                status="transcribing",
                current_step="transcribing",
                progress_percent=75,
                message=f"Transcribing audio with backend '{backend}' from {normalized_wav}",
            )
            transcript_text, language, source = self._transcribe_audio(video_id, normalized_wav)

            result = {
                "video_id": video_id,
                "transcript": transcript_text,
                "language": language or "unknown",
                "metadata": extract_basic_metadata(metadata).model_dump(),
                "source": source,
                "cache_used": False,
                "cached_at": None,
            }
            self.transcript_from_audio_cache_service.save_transcript(video_id, result)

            cached_result = self.transcript_from_audio_cache_service.get_cached_transcript(video_id) or result
            self._update_job_status(
                video_id,
                status="completed",
                current_step="completed",
                progress_percent=100,
                message=f"Transcript completed successfully using backend '{source}'",
                error=None,
                result=cached_result,
            )
        except Exception as e:
            self._update_job_status(
                video_id,
                status="failed",
                current_step="failed",
                progress_percent=100,
                message="Transcript processing failed",
                error=str(e),
            )
            raise
        finally:
            if settings.APP_JOB_CLEANUP_TEMP_FILES:
                logger.info("[%s] Cleaning temporary files from: %s", video_id, job_dir)
                shutil.rmtree(job_dir, ignore_errors=True)

    def _download_audio(self, video_id: str, output_base: Path) -> Path:
        url = f"https://www.youtube.com/watch?v={video_id}"
        outtmpl = str(output_base) + ".%(ext)s"
        options = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": settings.APP_YTDLP_SOCKET_TIMEOUT_SECONDS,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)

        downloaded_path = Path(path)
        if not downloaded_path.exists():
            candidates = sorted(output_base.parent.glob(output_base.name + ".*"))
            if not candidates:
                raise RuntimeError("Failed to locate downloaded audio file")
            downloaded_path = candidates[0]

        return downloaded_path

    def _extract_audio(self, source_path: Path, target_path: Path) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-ar",
            str(settings.APP_FFMPEG_AUDIO_RATE),
            "-ac",
            str(settings.APP_FFMPEG_AUDIO_CHANNELS),
            str(target_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg failed to normalize audio")

    def _transcribe_audio(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        backend = self.transcription_backend_service.get_backend_name()
        logger.info("[%s] Starting transcription with backend '%s' for %s", video_id, backend, audio_path)
        transcript_text, language, source = self.transcription_backend_service.transcribe(video_id, audio_path)
        logger.info("[%s] Transcription finished with backend '%s'", video_id, source)
        return transcript_text, language, source

    def _get_model(self, video_id: str):
        if self._model is None:
            logger.info("[%s] Loading faster-whisper model '%s' on device '%s'", video_id, settings.APP_WHISPER_MODEL, settings.APP_WHISPER_DEVICE)
            self._model = WhisperModel(
                settings.APP_WHISPER_MODEL,
                device=settings.APP_WHISPER_DEVICE,
                compute_type=settings.APP_WHISPER_COMPUTE_TYPE,
            )
            logger.info("[%s] faster-whisper model is ready", video_id)
        return self._model

    def _update_job_status(self, video_id: str, **updates) -> dict:
        job = self.job_service.update_job(video_id, **updates)
        logger.info(
            "[%s] status=%s step=%s progress=%s%% message=%s",
            video_id,
            job.get("status", "unknown"),
            job.get("current_step", "unknown"),
            job.get("progress_percent", 0),
            job.get("message", ""),
        )
        if job.get("error"):
            logger.error("[%s] error=%s", video_id, job.get("error"))
        return job
