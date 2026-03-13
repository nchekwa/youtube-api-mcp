from typing import Any


from app.models import AudioTranscriptPayload, BasicVideoMetadata, TranscriptPayload


def extract_basic_metadata(metadata: dict[str, Any]) -> BasicVideoMetadata:
    return BasicVideoMetadata(
        title=metadata.get("title", "Unknown"),
        author=metadata.get("author", metadata.get("uploader", "Unknown")),
        duration=metadata.get("duration", 0),
        publish_date=metadata.get("upload_date", metadata.get("publish_date", "Unknown")),
        view_count=metadata.get("view_count", 0),
        thumbnail=metadata.get("thumbnail"),
        description=metadata.get("description"),
    )


def build_direct_transcript_payload(data: dict[str, Any] | None) -> TranscriptPayload | None:
    if not data or not data.get("transcript"):
        return None

    return TranscriptPayload(
        transcript=data.get("transcript", ""),
        language=data.get("language", "unknown"),
        source="youtube",
        cache_used=data.get("cache_used", False),
        cached_at=data.get("cached_at"),
    )


def build_audio_transcript_payload(data: dict[str, Any] | None) -> AudioTranscriptPayload | None:
    if not data or not data.get("transcript"):
        return None

    return AudioTranscriptPayload(
        transcript=data.get("transcript", ""),
        language=data.get("language", "unknown"),
        source=data.get("source", "unknown"),
        cache_used=data.get("cache_used", False),
        cached_at=data.get("cached_at"),
    )


def build_audio_job_message(reason: str, transcript_from_audio_status: dict[str, Any]) -> str:
    status = transcript_from_audio_status.get("status", "queued")
    video_id = transcript_from_audio_status.get("video_id", "unknown")
    background_message = transcript_from_audio_status.get("message", "Background audio transcription was queued.")
    suffix = "Audio transcription is already available." if status == "completed" else "Check the audio transcription status using the same video_id."
    return (
        f"Direct YouTube transcript fetch failed: {reason}. "
        f"Audio transcription status for video_id {video_id} is '{status}'. "
        f"Background transcription message: {background_message}. "
        f"{suffix}"
    )
