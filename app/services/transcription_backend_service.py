from __future__ import annotations

from pathlib import Path
from typing import Callable
import json
import mimetypes
import time

import httpx

from app.config import settings


class TranscriptionBackendService:
    def __init__(
        self,
        update_job_status: Callable[..., dict],
        get_local_model: Callable[[str], object],
    ):
        self._update_job_status = update_job_status
        self._get_local_model = get_local_model

    def get_backend_name(self) -> str:
        raw_backend = settings.APP_TRANSCRIPTION_BACKEND or ""
        return raw_backend.split("#", 1)[0].strip().lower()

    def get_backend_model_key(self) -> str:
        backend = self.get_backend_name()
        if backend == "faster-whisper":
            return settings.APP_WHISPER_MODEL
        if backend == "openai":
            return self._get_model_name("gpt-4o-mini-transcribe")
        if backend == "assembly":
            return self._get_model_name("universal-3-pro,universal-2")
        if backend == "gemini":
            return self._get_model_name("gemini-2.5-flash")
        return backend

    def transcribe(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        backend = self.get_backend_name()
        if backend == "faster-whisper":
            return self._transcribe_with_faster_whisper(video_id, audio_path)
        if backend == "openai":
            return self._transcribe_with_openai(video_id, audio_path)
        if backend == "assembly":
            return self._transcribe_with_assembly(video_id, audio_path)
        if backend == "gemini":
            return self._transcribe_with_gemini(video_id, audio_path)
        raise RuntimeError(f"Unsupported transcription backend: {settings.APP_TRANSCRIPTION_BACKEND}")

    def _transcribe_with_faster_whisper(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        model = self._get_local_model(video_id)
        segments, info = model.transcribe(str(audio_path))
        transcript_parts: list[str] = []
        audio_duration = max(float(getattr(info, "duration", 0) or 0), 1.0)
        last_progress = 75

        for segment in segments:
            segment_text = segment.text.strip()
            if segment_text:
                transcript_parts.append(segment_text)

            segment_end = float(getattr(segment, "end", 0) or 0)
            transcribe_ratio = min(max(segment_end / audio_duration, 0.0), 1.0)
            progress_percent = min(95, 75 + int(transcribe_ratio * 20))

            if progress_percent > last_progress:
                last_progress = progress_percent
                self._update_job_status(
                    video_id,
                    status="transcribing",
                    current_step="transcribing",
                    progress_percent=progress_percent,
                    message=f"Transcribing audio with faster-whisper from {audio_path} ({progress_percent}%)",
                )

        transcript_text = " ".join(transcript_parts).strip()
        if not transcript_text:
            raise RuntimeError("Transcription produced an empty transcript")
        return transcript_text, getattr(info, "language", "unknown"), "faster-whisper"

    def _transcribe_with_openai(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("APP_API_KEY is not configured for backend 'openai'")

        base_url = self._get_base_url("https://api.openai.com/v1")
        model_name = self._get_model_name("gpt-4o-mini-transcribe")

        mime_type = self._get_mime_type(audio_path)
        self._update_job_status(
            video_id,
            status="uploading_audio",
            current_step="uploading_audio",
            progress_percent=68,
            message=f"Uploading audio to OpenAI from {audio_path}",
        )

        with httpx.Client(timeout=settings.APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS) as client:
            with open(audio_path, "rb") as audio_file:
                response = client.post(
                    f"{base_url.rstrip('/')}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={
                        "model": model_name,
                        "response_format": "verbose_json",
                    },
                    files={"file": (audio_path.name, audio_file, mime_type)},
                )

        self._raise_for_status(response, "OpenAI transcription request failed")
        payload = response.json()
        transcript_text = str(payload.get("text", "")).strip()
        if not transcript_text:
            raise RuntimeError("OpenAI transcription produced an empty transcript")
        return transcript_text, str(payload.get("language", "unknown") or "unknown"), "openai"

    def _transcribe_with_assembly(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("APP_API_KEY is not configured for backend 'assembly'")

        base_url = self._get_base_url("https://api.assemblyai.com").rstrip("/")
        speech_models = [
            model.strip()
            for model in self._get_model_name("universal-3-pro,universal-2").split(",")
            if model.strip()
        ]
        language_detection = self._get_language_detection()
        headers = {"authorization": api_key}

        self._update_job_status(
            video_id,
            status="uploading_audio",
            current_step="uploading_audio",
            progress_percent=68,
            message=f"Uploading audio to AssemblyAI from {audio_path}",
        )

        with httpx.Client(timeout=settings.APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS) as client:
            with open(audio_path, "rb") as audio_file:
                upload_response = client.post(
                    f"{base_url}/v2/upload",
                    headers=headers,
                    content=audio_file.read(),
                )
            self._raise_for_status(upload_response, "AssemblyAI upload failed")
            upload_url = upload_response.json().get("upload_url")
            if not upload_url:
                raise RuntimeError("AssemblyAI did not return upload_url")

            self._update_job_status(
                video_id,
                status="awaiting_provider",
                current_step="awaiting_provider",
                progress_percent=78,
                message="Waiting for AssemblyAI transcription result",
            )

            transcript_response = client.post(
                f"{base_url}/v2/transcript",
                headers=headers,
                json={
                    "audio_url": upload_url,
                    "speech_models": speech_models,
                    "language_detection": language_detection,
                },
            )
            self._raise_for_status(transcript_response, "AssemblyAI transcript request failed")
            transcript_id = transcript_response.json().get("id")
            if not transcript_id:
                raise RuntimeError("AssemblyAI did not return transcript id")

            started_at = time.monotonic()
            progress_percent = 79
            while True:
                if time.monotonic() - started_at > settings.APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS:
                    raise RuntimeError("AssemblyAI transcription polling timed out")

                poll_response = client.get(f"{base_url}/v2/transcript/{transcript_id}", headers=headers)
                self._raise_for_status(poll_response, "AssemblyAI transcript polling failed")
                payload = poll_response.json()
                status = payload.get("status")

                if status == "completed":
                    transcript_text = str(payload.get("text", "")).strip()
                    if not transcript_text:
                        raise RuntimeError("AssemblyAI transcription produced an empty transcript")
                    language = str(payload.get("language_code", "unknown") or "unknown")
                    return transcript_text, language, "assembly"

                if status == "error":
                    raise RuntimeError(str(payload.get("error", "AssemblyAI transcription failed")))

                progress_percent = min(95, progress_percent + 1)
                self._update_job_status(
                    video_id,
                    status="awaiting_provider",
                    current_step="awaiting_provider",
                    progress_percent=progress_percent,
                    message=f"AssemblyAI is processing audio from {audio_path} ({progress_percent}%)",
                )
                time.sleep(settings.APP_TRANSCRIPTION_PROVIDER_POLL_SECONDS)

    def _transcribe_with_gemini(self, video_id: str, audio_path: Path) -> tuple[str, str, str]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("APP_API_KEY is not configured for backend 'gemini'")

        base_url = self._get_base_url("https://generativelanguage.googleapis.com")
        model_name = self._get_model_name("gemini-2.5-flash")

        mime_type = self._get_mime_type(audio_path)
        headers = {
            "x-goog-api-key": api_key,
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(audio_path.stat().st_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
        }

        self._update_job_status(
            video_id,
            status="uploading_audio",
            current_step="uploading_audio",
            progress_percent=68,
            message=f"Uploading audio to Gemini from {audio_path}",
        )

        with httpx.Client(timeout=settings.APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS) as client:
            start_response = client.post(
                f"{base_url.rstrip('/')}/upload/v1beta/files",
                headers={**headers, "Content-Type": "application/json"},
                content=json.dumps({"file": {"display_name": audio_path.name}}),
            )
            self._raise_for_status(start_response, "Gemini upload session start failed")
            upload_url = start_response.headers.get("x-goog-upload-url")
            if not upload_url:
                raise RuntimeError("Gemini upload URL not returned")

            with open(audio_path, "rb") as audio_file:
                upload_response = client.post(
                    upload_url,
                    headers={
                        "Content-Length": str(audio_path.stat().st_size),
                        "X-Goog-Upload-Offset": "0",
                        "X-Goog-Upload-Command": "upload, finalize",
                    },
                    content=audio_file.read(),
                )
            self._raise_for_status(upload_response, "Gemini file upload failed")
            file_payload = upload_response.json()
            file_info = file_payload.get("file", {})
            file_uri = file_info.get("uri")
            file_mime_type = file_info.get("mimeType") or mime_type
            if not file_uri:
                raise RuntimeError("Gemini file URI not returned")

            self._update_job_status(
                video_id,
                status="awaiting_provider",
                current_step="awaiting_provider",
                progress_percent=80,
                message=f"Requesting Gemini transcription for {audio_path}",
            )

            response = client.post(
                f"{base_url.rstrip('/')}/v1beta/models/{model_name}:generateContent",
                params={"key": api_key},
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": settings.APP_GEMINI_TRANSCRIPTION_PROMPT},
                                {"file_data": {"mime_type": file_mime_type, "file_uri": file_uri}},
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                    },
                },
            )

        self._raise_for_status(response, "Gemini transcription request failed")
        payload = response.json()
        transcript_payload = self._extract_gemini_payload(payload)
        transcript_text = str(transcript_payload.get("transcript", "")).strip()
        if not transcript_text:
            raise RuntimeError("Gemini transcription produced an empty transcript")
        language = str(transcript_payload.get("language", "unknown") or "unknown")
        return transcript_text, language, "gemini"

    def _extract_gemini_payload(self, payload: dict) -> dict:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini returned no content parts")

        raw_text = str(parts[0].get("text", "")).strip()
        if not raw_text:
            raise RuntimeError("Gemini returned empty text")

        cleaned = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"transcript": raw_text, "language": "unknown"}

        if isinstance(data, dict):
            return data
        return {"transcript": raw_text, "language": "unknown"}

    def _raise_for_status(self, response: httpx.Response, default_message: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text.strip()
            message = response_text or default_message
            raise RuntimeError(message) from exc

    def _get_api_key(self) -> str:
        return settings.APP_API_KEY.strip()

    def _get_base_url(self, default_value: str) -> str:
        return (settings.APP_BASE_URL or default_value).strip()

    def _get_model_name(self, default_value: str) -> str:
        return (settings.APP_MODEL or default_value).strip()

    def _get_language_detection(self) -> bool:
        return settings.APP_LANGUAGE_DETECTION

    def _get_mime_type(self, audio_path: Path) -> str:
        return mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
