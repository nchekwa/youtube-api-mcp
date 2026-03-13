from typing import Any
from pydantic import BaseModel, Field


class BasicVideoMetadata(BaseModel):
    """Basic normalized metadata returned by transcript endpoints."""
    title: str = Field(default="Unknown", description="Video title")
    author: str = Field(default="Unknown", description="Channel or author name")
    duration: int = Field(default=0, description="Video duration in seconds")
    publish_date: str = Field(default="Unknown", description="Publish date")
    view_count: int = Field(default=0, description="Number of views")
    thumbnail: str | None = Field(default=None, description="Thumbnail URL")
    description: str | None = Field(default=None, description="Video description")


class TranscriptPayload(BaseModel):
    """Normalized transcript payload for direct YouTube transcripts."""
    transcript: str = Field(..., description="Full transcript text")
    language: str = Field(default="unknown", description="Transcript language code")
    source: str = Field(default="youtube", description="Transcript source")
    cache_used: bool = Field(default=False, description="Whether payload came from cache")
    cached_at: str | None = Field(default=None, description="ISO timestamp when cached")


class AudioTranscriptPayload(BaseModel):
    """Normalized transcript payload for audio transcription results."""
    transcript: str = Field(..., description="Full transcript text")
    language: str = Field(default="unknown", description="Transcript language code")
    source: str = Field(default="unknown", description="Audio transcription backend")
    cache_used: bool = Field(default=False, description="Whether payload came from cache")
    cached_at: str | None = Field(default=None, description="ISO timestamp when cached")


class TranscriptResponse(BaseModel):
    """Transcript response with separate direct and audio transcript payloads."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    metadata: BasicVideoMetadata = Field(..., description="Normalized video metadata")
    transcript_youtube: TranscriptPayload | None = Field(default=None, description="Direct YouTube transcript payload")
    transcript_audio: AudioTranscriptPayload | None = Field(default=None, description="Audio transcription payload")
    source_preference: list[str] = Field(default_factory=list, description="Requested transcript source preference order")


class TranscriptRequestAcceptedResponse(BaseModel):
    """Response returned when direct transcript fetching falls back to background audio transcription."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    status: str = Field(..., description="Background transcription status")
    message: str = Field(..., description="Human-readable queue status")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Background transcription progress")
    transcript_from_audio_reason: str = Field(..., description="Original direct transcript failure reason from YouTube")
    result: AudioTranscriptPayload | None = Field(default=None, description="Completed audio transcript result when already available")


class RawTranscriptResponse(BaseModel):
    """Transcript response with full metadata payload."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    metadata: dict[str, Any] = Field(..., description="Full yt-dlp metadata")
    transcript_youtube: TranscriptPayload | None = Field(default=None, description="Direct YouTube transcript payload")
    transcript_audio: AudioTranscriptPayload | None = Field(default=None, description="Audio transcription payload")
    source_preference: list[str] = Field(default_factory=list, description="Requested transcript source preference order")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    uptime_seconds: float = Field(..., ge=0, description="Application uptime in seconds")
    transcription_backend: str = Field(..., description="Configured transcription backend")
    transcript_from_audio_enabled: bool = Field(..., description="Whether audio transcription fallback is enabled")
    cache_path: str = Field(..., description="Cache directory path")
    cache_accessible: bool = Field(..., description="Whether cache directory is accessible")
    whisper_model_loaded: bool = Field(..., description="Whether the local Whisper model is loaded in memory")

class CacheResponse(BaseModel):
    """Cache check response."""
    status: str = Field(..., description="Service status")
    cache_size: int = Field(..., ge=0, description="Number of cached items")
    cache_path: str = Field(..., description="Cache directory path")
    cache_size_bytes: int = Field(..., ge=0, description="Total cache size in bytes")
    cache_size_mb: float = Field(..., ge=0, description="Total cache size in megabytes")
    max_cache_size_mb: int = Field(..., ge=0, description="Configured maximum cache size in megabytes")


class CacheEntryResponse(BaseModel):
    """Cache entry metadata returned by cache management endpoints."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    file_name: str = Field(..., description="Cache file name")
    size_bytes: int = Field(..., ge=0, description="Cache file size in bytes")
    updated_at: str = Field(..., description="Last modification timestamp in ISO format")


class CacheListResponse(BaseModel):
    """Cache listing response."""
    status: str = Field(..., description="Service status")
    entries: list[CacheEntryResponse] = Field(default_factory=list, description="Cache entries")
    cache_size: int = Field(..., ge=0, description="Number of cached items")
    cache_size_bytes: int = Field(..., ge=0, description="Total cache size in bytes")
    cache_size_mb: float = Field(..., ge=0, description="Total cache size in megabytes")
    max_cache_size_mb: int = Field(..., ge=0, description="Configured maximum cache size in megabytes")


class CacheClearResponse(BaseModel):
    """Cache clear response."""
    success: bool = Field(..., description="Whether the cache operation succeeded")
    message: str = Field(..., description="Human-readable operation result")
    deleted_entries: int = Field(default=0, ge=0, description="Number of deleted cache entries")


class TranscriptFromAudioResult(BaseModel):
    """Transcript payload produced from the audio track."""
    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    transcript: str = Field(..., description="Full transcript text")
    language: str = Field(default="unknown", description="Detected transcript language code")
    metadata: BasicVideoMetadata = Field(..., description="Basic yt-dlp metadata")
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
