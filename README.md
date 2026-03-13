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

Returns cache statistics and service health.

**Response:**
```json
{
  "status": "healthy",
  "cache_size": 42,
  "cache_path": "/app/cache"
}
```

### 2. Get Transcript with Basic Metadata

```bash
GET /api/v1/youtube/transcript/{video_id}?use_cache=true
```

When `_APP_TRANSCRIPT_FROM_AUDIO=true`, this endpoint can automatically queue `transcript_from_audio` processing if direct YouTube transcript fetch fails for reasons such as disabled transcripts or YouTube-side access issues. `Video unavailable` remains a hard error.

**Parameters:**
- `video_id` (path): YouTube video ID (11 chars) or full URL
  - Examples: `mQ-y2ZOTpr4` or `https://www.youtube.com/watch?v=mQ-y2ZOTpr4`
- `use_cache` (query): Enable/disable cache (default: `true`)

**Returns basic metadata (7 fields):**
- `title` - Video title
- `author` - Channel/author name
- `duration` - Duration in seconds
- `publish_date` - Upload date (YYYY-MM-DD)
- `view_count` - Number of views
- `thumbnail` - URL to video thumbnail (can be null)
- `description` - Full video description (can be null)

**Response:**
```json
{
  "video_id": "mQ-y2ZOTpr4",
  "transcript": "Full transcript text here...",
  "language": "en",
  "cache_used": false,
  "cached_at": null,
  "metadata": {
    "title": "Video Title",
    "author": "Channel Name",
    "duration": 218,
    "publish_date": "20251203",
    "view_count": 9084,
    "thumbnail": "https://i.ytimg.com/vi/...",
    "description": "Full description..."
  }
}
```

**Transcript_from_audio response when direct transcript fetch fails and `_APP_TRANSCRIPT_FROM_AUDIO=true`:**
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

**Example:**
```bash
curl "http://localhost:8000/api/v1/youtube/transcript/mQ-y2ZOTpr4"
```

### 3. Get Transcript with Full Metadata

```bash
GET /api/v1/youtube/transcript/raw/{video_id}?use_cache=true
```

Returns **complete yt-dlp metadata** (50+ fields) including:
- Basic: title, author, duration, views, upload date
- Engagement: likes, comments
- Media: description, thumbnails, categories, tags
- Technical: resolution, codecs, format, filesize
- Channel: channel_id, subscribers, location
- Subtitles: available and auto-generated captions

**Example:**
```bash
curl "http://localhost:8000/api/v1/youtube/transcript/raw/mQ-y2ZOTpr4"
```

### 4. Root Endpoint

```bash
GET /
```

Returns API information and available endpoints.

### 5. Queue Local Audio Transcription

```bash
POST /api/v1/youtube/audio-transcript/{video_id}
```

Queues background transcription for the provided `video_id`, downloads the video's audio track, normalizes it with `ffmpeg`, transcribes it with the configured backend, and stores the result under `transcript_from_audio` in cache.

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

If `transcript_from_audio` already exists in cache, the endpoint returns `completed` and includes the cached result immediately.

### 6. Check Background Transcription Status

```bash
GET /api/v1/youtube/audio-transcript/{video_id}
```

Returns the current background transcription state with step-level progress:
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

## Behavior

### Language Handling

The API always returns the **first available transcript** (usually the native/original language):
- Prefers: Manual transcripts over auto-generated ones
- No language parameter needed
- Response includes `language` field to indicate which language was returned
- Cache: Stored as `video_id.json` (one file per video)

### Cache Logic

1. First checks cache for video ID
2. If not in cache: Fetches from YouTube (first available transcript)
3. Saves to cache as `<video_id>.json` under `direct_from_youtube`
4. Next request: Returns cached data with `cache_used: true`
5. If `transcript_from_audio` also exists in the same cache file, the standard transcript response keeps the direct transcript first and appends an extra `[TRANSCRIPT FROM AUDIO TRACK]` section below it

If `_APP_TRANSCRIPT_FROM_AUDIO=true` and direct transcript fetch fails for a transcript_from_audio-eligible reason, the standard transcript endpoint and MCP `get_youtube_transcript` tool automatically queue or reuse background audio transcription for the same `video_id`.

### Transcript From Audio Logic

1. The transcript_from_audio request endpoint normalizes the input to `video_id`
2. It checks `cache/<video_id>.json` for `transcript_from_audio`
3. If not cached, it creates or reuses a file-backed background status entry in `cache/jobs/`, keyed by `video_id`
4. The worker downloads audio with `yt-dlp`
5. `ffmpeg` converts audio to a mono 16k WAV file suitable for transcription backends
6. The configured backend generates the final transcript:
   - `faster-whisper` runs locally
   - `assembly` uploads audio and polls AssemblyAI
   - `openai` sends audio to the OpenAI transcription API
   - `gemini` uploads audio and requests structured transcription output
7. Result is stored in `cache/<video_id>.json` under `transcript_from_audio` and exposed through HTTP and MCP polling
8. If `transcript_from_audio` already exists in `cache/<video_id>.json`, a new audio transcription job is not created again for that video
9. Logs include the active backend and the working file paths used during processing

## Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## MCP Server

MCP (Model Context Protocol) server is integrated with FastAPI and supports **StreamableHttpTransport** (recommended for production).

Set `_APP_MCP_HIDE_CLEAR_CACHE=true` to hide the `clear_cache` tool from the MCP tools list. By default it remains visible.

- **MCP Endpoint**: `http://localhost:8000/api/v1/mcp`
- **Transport**: StreamableHttpTransport (efficient bidirectional streaming over HTTP)
- **Tools**:
  - `get_youtube_transcript` - Fetch transcript with basic metadata from YouTube video (first available language)
  - `request_youtube_audio_transcript` - Queue transcript_from_audio generation using the configured backend unless `transcript_from_audio` already exists in `cache/<video_id>.json`
  - `get_youtube_audio_transcript` - Poll background transcription status/result by `video_id`
  - `clear_cache` - Clear the shared cached transcript file for a specific video, including `direct_from_youtube` and `transcript_from_audio` sections stored in `<video_id>.json` (visible by default, hidden when `_APP_MCP_HIDE_CLEAR_CACHE=true`)

### MCP Tool Example

```python
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_transport

async with streamable_http_transport("http://localhost:8000/api/v1/mcp") as transport:
    async with ClientSession(transport) as session:
        # Initialize connection
        await session.initialize()

        # List available tools
        tools = await session.list_tools()

        # Get transcript
        result = await session.call_tool(
            "get_youtube_transcript",
            arguments={"video_id": "9Wg6tiaar9M"}
        )

        # Queue transcript_from_audio generation
        result = await session.call_tool(
            "request_youtube_audio_transcript",
            arguments={"video_id": "9Wg6tiaar9M"}
        )

        # Poll status by the same video_id
        result = await session.call_tool(
            "get_youtube_audio_transcript",
            arguments={"video_id": "9Wg6tiaar9M"}
        )
```

### MCP Config (for IDEs)

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

All environment variables must have `_APP_` prefix. Create `.env` file from `.env.example`:

```bash
# ======================
# API PATHS
# ======================
_APP_ROOT_PATH=                           # Root path for API (default: empty string)
_APP_API_PREFIX=/api/v1                   # API prefix for all endpoints (default: /api/v1)

# ======================
# CACHE CONFIGURATION
# ======================
_APP_CACHE_DIR=./cache                    # Directory for cache storage (default: ./cache)
_APP_MAX_CACHE_SIZE_MB=1000               # Maximum cache size in megabytes (default: 1000)
_APP_CACHE_TTL_DAYS=30                    # Cache time-to-live in days (default: 30)
_APP_JOBS_DIR=./cache/jobs                # Directory for background transcription status JSON files keyed by video_id
_APP_WORK_DIR=./cache/work                # Directory for temporary audio work files

# ======================
# FUNCTIONALITY
# ======================
_APP_USE_CACHE_DEFAULT=true               # Enable caching by default (default: true)
_APP_TRANSCRIPT_FROM_AUDIO=false          # Auto-queue transcript_from_audio processing when direct YouTube transcript fetch fails
_APP_BACKGROUND_JOB_CONCURRENCY=1         # Number of concurrent background transcription workers
_APP_JOB_POLL_TTL_DAYS=7                  # Days to retain old background transcription status files
_APP_JOB_CLEANUP_TEMP_FILES=true          # Remove temp audio files after processing

# ======================
# TRANSCRIPTION
# ======================
_APP_TRANSCRIPTION_BACKEND=faster-whisper # Backend: faster-whisper|assembly|openai|gemini
_APP_WHISPER_MODEL=large-v3               # Whisper model name for faster-whisper
_APP_WHISPER_DEVICE=cpu                   # Device: cpu or cuda
_APP_WHISPER_COMPUTE_TYPE=int8            # Compute type for faster-whisper
_APP_YTDLP_SOCKET_TIMEOUT_SECONDS=120     # yt-dlp socket timeout in seconds
_APP_FFMPEG_AUDIO_RATE=16000              # Output WAV sample rate
_APP_FFMPEG_AUDIO_CHANNELS=1              # Output WAV channel count
_APP_TRANSCRIPTION_PROVIDER_TIMEOUT_SECONDS=1800 # Timeout for external transcription providers in seconds
_APP_TRANSCRIPTION_PROVIDER_POLL_SECONDS=3       # Poll interval for asynchronous providers in seconds
_APP_API_KEY=                              # API key for selected external backend
_APP_BASE_URL=                             # Base URL for selected external backend
_APP_MODEL=                                # Model for selected backend (AssemblyAI accepts CSV, e.g. universal-3-pro,universal-2)
_APP_LANGUAGE_DETECTION=true               # Language detection flag for selected backend
_APP_GEMINI_TRANSCRIPTION_PROMPT=Transcribe this audio verbatim. Return JSON with keys 'transcript' and 'language'.

# ======================
# API KEY AUTHENTICATION
# ======================
_APP_X_API_KEY=                           # API key for authentication (leave empty to disable)
_APP_X_API_KEY_HEADER=X-API-Key           # HTTP header name for API key (default: X-API-Key)

# ======================
# SYSTEM
# ======================
_APP_LOG_LEVEL=INFO                       # Logging level: DEBUG|INFO|WARNING|ERROR|CRITICAL (default: INFO)
_APP_PORT=8000                            # Server port number (default: 8000)
```

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

```
app/
├── main.py                 # FastAPI application setup
├── config.py               # Configuration with Pydantic Settings
├── models.py               # Pydantic models (TranscriptResponse, HealthResponse)
├── middleware/
│   ├── auth.py            # API key authentication
│   └── process_time.py    # Request timing middleware
├── routers/
│   ├── transcript.py     # Primary transcript endpoints
│   └── transcript_from_audio.py # Background transcript_from_audio endpoints
├── services/
│   ├── cache_service.py   # Cache management (read, write, TTL)
│   ├── transcript_from_audio_cache_service.py # Transcript_from_audio cache access
│   ├── job_service.py     # File-backed job registry
│   ├── background_transcription_service.py # Audio download/extract/transcribe pipeline orchestration
│   ├── transcription_backend_service.py # Backend dispatch for faster-whisper, AssemblyAI, OpenAI, Gemini
│   └── youtube_service.py # YouTube integration (yt-dlp)
└── mcp/
    └── server.py          # MCP server with tools
```

## Development

### Project Status

Current version: 1.0.0

All features implemented:
- ✅ Cache service (init, read, write, size tracking, TTL)
- ✅ YouTube service (fetch transcript, full metadata, first available language)
- ✅ API endpoints (transcript, raw, health)
- ✅ Rate limiting (30 req/min default)
- ✅ Docker configuration
- ✅ MCP server integration
- ✅ Background transcript_from_audio processing with progress polling
- ✅ Selectable transcription backends: faster-whisper, AssemblyAI, OpenAI, Gemini
- ✅ Timestamped development logging with visible active backend and log level
- ✅ API key authentication (optional)
- ✅ Environment variables with `_APP_` prefix
- ✅ Full Swagger/OpenAPI documentation

## Cache Structure

Cache files are stored as JSON:
```
cache/
├── {video_id}.json
├── jobs/
│   └── {video_id}.json
└── work/
```

Each cache file contains:
- `video_id` - YouTube video ID
- `direct_from_youtube` - Cached direct transcript payload from YouTube
- `transcript_from_audio` - Cached transcript payload generated from the audio track

## License

MIT
