from datetime import datetime
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


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")

class CacheResponse(BaseModel):
    """Cache check response."""
    status: str = Field(..., description="Service status")
    cache_size: int = Field(..., ge=0, description="Number of cached items")
    cache_path: str = Field(..., description="Cache directory path")
