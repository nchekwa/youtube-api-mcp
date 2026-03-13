from typing import Any
from pydantic import BaseModel, Field, field_validator


class TranscriptResponse(BaseModel):
    """Complete transcript response with basic metadata and text."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    transcript: str = Field(..., description="Full transcript text")
    language: str = Field(default="unknown", description="Transcript language code (first available)")
    cache_used: bool = Field(default=False, description="Whether response came from cache")
    cached_at: str | None = Field(default=None, description="ISO timestamp when cached (null if not from cache)")
    metadata: dict[str, Any] = Field(..., description="Basic yt-dlp metadata")


class TranscriptFromAudioResponse(BaseModel):
    """Response returned when direct YouTube transcript fetch switches to transcript_from_audio processing."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    status: str = Field(..., description="Background transcription status")
    message: str = Field(..., description="Human-readable explanation and transcript_from_audio queue status")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Background transcription progress")
    transcript_from_audio_reason: str = Field(..., description="Original direct transcript failure reason from YouTube")
    result: dict[str, Any] | None = Field(default=None, description="Completed transcript_from_audio result when already available")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")

class CacheResponse(BaseModel):
    """Cache check response."""
    status: str = Field(..., description="Service status")
    cache_size: int = Field(..., ge=0, description="Number of cached items")
    cache_path: str = Field(..., description="Cache directory path")


class TranscriptFromAudioResult(BaseModel):
    """Transcript payload produced from the audio track."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    transcript: str = Field(..., description="Full transcript text")
    language: str = Field(default="unknown", description="Detected transcript language code")
    metadata: dict[str, Any] = Field(..., description="Basic yt-dlp metadata")
    source: str = Field(default="local_whisper", description="Transcript source backend")
    cache_used: bool = Field(default=False, description="Whether response came from transcript_from_audio cache")
    cached_at: str | None = Field(default=None, description="ISO timestamp when cached")


class BackgroundTranscriptRequestResponse(BaseModel):
    """Response returned when creating or reusing a background transcription entry for a video."""
    status: str = Field(..., description="Current background transcription or cache status")
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    message: str = Field(..., description="Human-readable status message")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Background transcription progress")
    result: TranscriptFromAudioResult | None = Field(default=None, description="Transcript_from_audio result when already available")


class BackgroundTranscriptJobResponse(BaseModel):
    """Detailed status for background transcription tracked by video_id."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    status: str = Field(..., description="Background transcription state")
    current_step: str = Field(..., description="Current processing step")
    message: str = Field(..., description="Human-readable status message")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Background transcription progress")
    created_at: str = Field(..., description="Status creation timestamp")
    updated_at: str = Field(..., description="Status update timestamp")
    error: str | None = Field(default=None, description="Failure details if transcription failed")
    result: TranscriptFromAudioResult | None = Field(default=None, description="Transcript_from_audio result when completed")
