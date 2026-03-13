# YouTube Transcript API Service

API service to fetch YouTube video transcripts with metadata and local file caching.

## Features

- 📥 Fetch YouTube video transcripts with metadata
- 🎧 `transcript_from_audio` generation using `yt-dlp` + `ffmpeg` with selectable backend: `faster-whisper`, `assembly`, `openai`, or `gemini`
- 🧵 Background transcription jobs with progress polling
- 🪵 Timestamped development logs with visible active log level and transcription backend at startup
- 💾 Local file caching with TTL (30 days default)
- 🌍 Always returns first available transcript (native/original language)
- 🐳 Docker support
- 🔌 MCP (Model Context Protocol) server integration
- 📚 Interactive Swagger documentation
- ⚡ Rate limiting
- 🔒 Optional API key authentication
- 🖼️ Basic metadata includes: title, author, duration, views, publish date, thumbnail, description
- 📊 Full metadata endpoint with all yt-dlp fields (50+ fields)

## Quick Start

### Local Development

```bash
# Install dependencies
sudo apt install python3-venv ffmpeg
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt

# Copy environment variables and configure
cp .env.example .env
# Edit .env if needed

# Run server in dev mode (with hot-reload, no __pycache__)
./run-api-dev.sh
```

The development startup script:

- loads `.env` from the project root if present
- shows the active log level
- shows the active transcription backend
- enables timestamped Uvicorn logs through `app/uvicorn_log_config.json`

Or manually:

```bash
PYTHONDONTWRITEBYTECODE=1 uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-config app/uvicorn_log_config.json
```

### Docker

Docker uses a glibc-based Python image for compatibility with `faster-whisper` and `ctranslate2`, which are not reliably installable on `python:3.14-alpine`.

```bash
# Copy environment variables
cp .env.example .env
# Edit .env if needed

# Build and run with Docker Compose
sudo docker-compose up --build

# Or build and run manually
sudo docker build -t youtube-transcript-api .
sudo docker run -p 8000:8000 -v $(pwd)/cache:/app/cache youtube-transcript-api
```

## API Endpoints

### 1. Health Check

```bash
GET /api/v1/health
```

Returns application health and runtime information.

**Response:**

```json
{
  "status": "healthy",
  "version": "1.1.0",
  "uptime_seconds": 12.34,
  "transcription_backend": "faster-whisper",
  "transcript_from_audio_enabled": true,
  "cache_path": "/app/cache",
  "cache_accessible": true,
  "whisper_model_loaded": false
}
```

### 2. Get Transcript with Basic Metadata

```bash
GET /api/v1/youtube/transcript/{video_id}?use_cache=true&force_refresh=false&language=en
```

When `_APP_TRANSCRIPT_FROM_AUDIO=true`, this endpoint can automatically queue `transcript_from_audio` processing if direct YouTube transcript fetch fails for reasons such as disabled transcripts or YouTube-side access issues. `Video unavailable` remains a hard error.

**Parameters:**

- `video_id` (path): YouTube video ID (11 chars) or full URL
  - Examples: `mQ-y2ZOTpr4` or `https://www.youtube.com/watch?v=mQ-y2ZOTpr4`
- `use_cache` (query): Enable or disable cache lookup for direct YouTube transcripts
- `force_refresh` (query): Skip direct transcript cache lookup and overwrite the direct cache section
- `language` (query): Preferred transcript language code (optional)

**Returns:**

- `metadata` - Basic video metadata
- `transcript_youtube` - Direct transcript fetched from YouTube
- `transcript_audio` - Transcript generated from the audio track if available
- `source_preference` - Response source ordering metadata

**Response:**

```json
{
  "video_id": "mQ-y2ZOTpr4",
  "metadata": {
    "title": "Video Title",
    "author": "Channel Name",
    "duration": 218,
    "publish_date": "20251203",
    "view_count": 9084,
    "thumbnail": "https://i.ytimg.com/vi/...",
    "description": "Full description..."
  },
  "transcript_youtube": {
    "transcript": "Full transcript text here...",
    "language": "en",
    "source": "youtube",
    "cache_used": false,
    "cached_at": null
  },
  "transcript_audio": null,
  "source_preference": ["youtube", "audio"]
}
```

**Fallback response when direct transcript fetching queues audio transcription:**

```json
{
  "video_id": "3LbZP0sYmPw",
  "status": "queued",
  "message": "Direct YouTube transcript fetch failed: Transcripts are disabled for video 3LbZP0sYmPw. Transcript_from_audio status for video_id 3LbZP0sYmPw is 'queued'. Background transcription message: Transcript queued for background processing by video_id using backend 'assembly'. The transcript should be available in a few minutes. Check status by the same video_id.",
  "progress_percent": 0,
  "transcript_from_audio_reason": "Transcripts are disabled for video 3LbZP0sYmPw",
  "result": null
}
```

### 3. Get Transcript with Full Metadata

```bash
GET /api/v1/youtube/transcript/raw/{video_id}?use_cache=true&force_refresh=false&language=en
```

Returns complete `yt-dlp` metadata together with separated transcript payloads.

**Response:**

```json
{
  "video_id": "mQ-y2ZOTpr4",
  "metadata": {
    "title": "Video Title",
    "channel_id": "UC123..."
  },
  "transcript_youtube": {
    "transcript": "Full transcript text here...",
    "language": "en",
    "source": "youtube",
    "cache_used": true,
    "cached_at": "2026-03-13T12:34:56"
  },
  "transcript_audio": null,
  "source_preference": ["youtube", "audio"]
}
```

### 4. Queue Audio Transcription

```bash
POST /api/v1/youtube/audio-transcript/{video_id}
```

Queues background transcription for the provided `video_id`, downloads the audio track, normalizes it with `ffmpeg`, transcribes it with the configured backend, and stores the result under `transcript_from_audio` in cache.

Supported backends:

- `faster-whisper`
- `assembly`
- `openai`
- `gemini`

**Response:**

```json
{
  "status": "queued",
  "video_id": "mQ-y2ZOTpr4",
  "message": "Transcript queued for background processing by video_id using backend 'assembly'",
  "progress_percent": 0,
  "result": null
}
```

### 5. Check Background Transcription Status

```bash
GET /api/v1/youtube/audio-transcript/{video_id}
```

Returns the current background transcription state with step-level progress.

Possible states:

- `queued`
- `downloading_audio`
- `extracting_audio`
- `loading_model`
- `uploading_audio`
- `awaiting_provider`
- `transcribing`
- `completed`
- `failed`

**Response:**

```json
{
  "video_id": "mQ-y2ZOTpr4",
  "status": "transcribing",
  "current_step": "transcribing",
  "message": "Transcribing audio with backend 'assembly' from cache/work/mQ-y2ZOTpr4/audio.wav",
  "progress_percent": 70,
  "created_at": "2026-03-12T05:40:00",
  "updated_at": "2026-03-12T05:41:10",
  "error": null,
  "result": null
}
```

### 6. Cache Status

```bash
GET /api/v1/cache
```

**Response:**

```json
{
  "status": "healthy",
  "cache_size": 12,
  "cache_path": "./cache",
  "cache_size_bytes": 482102,
  "cache_size_mb": 0.46,
  "max_cache_size_mb": 1000
}
```

### 7. List Cache Entries

```bash
GET /api/v1/cache/entries
```

Requires API key authentication when enabled.

**Response:**

```json
{
  "status": "healthy",
  "entries": [
    {
      "video_id": "mQ-y2ZOTpr4",
      "file_name": "mQ-y2ZOTpr4.json",
      "size_bytes": 20480,
      "updated_at": "2026-03-13T20:00:00"
    }
  ],
  "cache_size": 1,
  "cache_size_bytes": 20480,
  "cache_size_mb": 0.02,
  "max_cache_size_mb": 1000
}
```

### 8. Clear All Cache Entries

```bash
DELETE /api/v1/cache
```

Requires API key authentication when enabled.

### 9. Clear Cache Entry By Video ID

```bash
DELETE /api/v1/cache/{video_id}
```

Requires API key authentication when enabled.

### 10. Root Endpoint

```bash
GET /
```

Returns API information and available endpoints.

## Behavior

### Language Handling

The API returns the best available transcript based on YouTube availability and your optional preferred language.

- Prefers manual transcripts over auto-generated ones
- Optional `language` query parameter can be used as a preferred transcript language hint
- Response separates direct and audio transcript payloads instead of concatenating them
- Cache is stored as `video_id.json` with separate sections for direct and audio transcripts

### Cache Logic

1. The API first checks cache by `video_id`.
2. If not found, it fetches a transcript from YouTube.
3. Direct transcripts are stored under `direct_from_youtube`.
4. Audio transcription results are stored under `transcript_from_audio`.
5. Cache size is limited by `_APP_MAX_CACHE_SIZE_MB`.
6. The oldest cache entries are evicted automatically after writes if the size limit is exceeded.

If `_APP_TRANSCRIPT_FROM_AUDIO=true` and direct transcript fetching fails for an eligible reason, the standard transcript endpoint and MCP `get_youtube_transcript` tool automatically queue or reuse background audio transcription for the same `video_id`.

### Transcript From Audio Logic

1. The request endpoint normalizes the input to `video_id`.
2. It checks `cache/<video_id>.json` for `transcript_from_audio`.
3. If not cached, it creates or reuses a file-backed background status entry in `cache/jobs/`.
4. The worker downloads audio with `yt-dlp`.
5. `ffmpeg` converts audio to mono 16k WAV.
6. The configured backend generates the final transcript.
7. The result is stored in cache and exposed through HTTP and MCP polling.

## Documentation

Interactive API documentation is available at:

- [Swagger UI](http://localhost:8000/docs)
- [ReDoc](http://localhost:8000/redoc)

## MCP Server

MCP (Model Context Protocol) server is integrated with FastAPI and supports `StreamableHttpTransport`.

Set `_APP_MCP_HIDE_CLEAR_CACHE=true` to hide the `clear_cache` tool from the MCP tools list.

- **MCP Endpoint**: `http://localhost:8000/api/v1/mcp`
- **Transport**: `streamable_http`
- **Tools**:
  - `get_youtube_transcript`
  - `request_youtube_audio_transcript`
  - `get_youtube_audio_transcript`
  - `clear_cache`

### MCP Tool Example

```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_transport

async with streamable_http_transport("http://localhost:8000/api/v1/mcp") as transport:
    async with ClientSession(transport) as session:
        await session.initialize()
        await session.call_tool(
            "get_youtube_transcript",
            arguments={"video_id": "9Wg6tiaar9M"},
        )
```

### MCP Config for IDEs

```json
{
  "mcpServers": {
    "youtube-transcript": {
      "url": "http://localhost:8000/api/v1/mcp",
      "transport": "streamable_http"
    }
  }
}
```

## Configuration

All environment variables use the `_APP_` prefix. Copy `.env.example` to `.env` and adjust values for your environment.

Key groups:

- API paths and CORS
- Cache, jobs, and work directories
- Transcript and audio fallback behavior
- Provider/backend configuration
- Optional API key authentication
- Logging and port binding

`_APP_API_KEY` is used only for external provider authentication. `_APP_X_API_KEY` independently enables API access control for incoming HTTP and MCP requests. Leaving `_APP_X_API_KEY` empty keeps incoming API and MCP authentication disabled.

### Backend Examples

#### Faster Whisper

```bash
_APP_TRANSCRIPTION_BACKEND=faster-whisper
_APP_WHISPER_MODEL=large-v3
_APP_WHISPER_DEVICE=cpu
_APP_WHISPER_COMPUTE_TYPE=int8
```

#### AssemblyAI

```bash
_APP_TRANSCRIPTION_BACKEND=assembly
_APP_API_KEY=your-assembly-api-key
_APP_BASE_URL=https://api.assemblyai.com
_APP_MODEL=universal-3-pro,universal-2
_APP_LANGUAGE_DETECTION=true
```

#### OpenAI

```bash
_APP_TRANSCRIPTION_BACKEND=openai
_APP_API_KEY=your-openai-api-key
_APP_BASE_URL=https://api.openai.com/v1
_APP_MODEL=gpt-4o-mini-transcribe
```

#### Gemini

```bash
_APP_TRANSCRIPTION_BACKEND=gemini
_APP_API_KEY=your-gemini-api-key
_APP_BASE_URL=https://generativelanguage.googleapis.com
_APP_MODEL=gemini-2.5-flash
```

## Architecture

```text
app/
├── main.py
├── config.py
├── models.py
├── middleware/
│   ├── auth.py
│   └── process_time.py
├── routers/
│   ├── transcript.py
│   └── transcript_from_audio.py
├── services/
│   ├── background_transcription_service.py
│   ├── cache_service.py
│   ├── job_service.py
│   ├── service_container.py
│   ├── transcription_backend_service.py
│   ├── transcript_from_audio_cache_service.py
│   └── youtube_service.py
├── utils/
│   └── transcript_utils.py
└── mcp/
    └── server.py
```

## Development

### Project Status

Current version: `1.1.0`

Implemented features:

- Cache service with TTL, atomic writes, and max-size eviction
- Direct transcript and audio transcript fallback flows
- Shared service container across REST and MCP
- REST cache management endpoints
- Optional CORS middleware
- Optional API key authentication
- Docker and Compose support
- Swagger and ReDoc documentation

## Cache Structure

Cache files are stored as JSON.

```text
cache/
├── {video_id}.json
├── jobs/
│   └── {video_id}.json
└── work/
```

Each cache file contains:

- `video_id`
- `direct_from_youtube`
- `transcript_from_audio`

## License

MIT
