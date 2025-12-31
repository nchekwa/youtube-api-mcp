# YouTube Transcript API Service

API service to fetch YouTube video transcripts with metadata and local file caching.

## Features

- 📥 Fetch YouTube video transcripts with metadata
- 💾 Local file caching with TTL (30 days default)
- 🌍 Multi-language support with automatic fallback to any available transcript
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
sudo apt install python3-venv
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt

# Copy environment variables and configure
cp .env.example .env
# Edit .env if needed

# Run server in dev mode (with hot-reload, no __pycache__)
./run-api-dev.sh
```

Or manually:
```bash
PYTHONDONTWRITEBYTECODE=1 uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
# Copy environment variables
cp .env.example .env
# Edit .env if needed

# Build and run with Docker Compose
docker-compose up --build

# Or build and run manually
docker build -t youtube-transcript-api .
docker run -p 8000:8000 -v $(pwd)/cache:/app/cache youtube-transcript-api
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
GET /api/v1/youtube/transcript/{video_id}?language=en&use_cache=true
```

**Parameters:**
- `video_id` (path): YouTube video ID (11 chars) or full URL
  - Examples: `mQ-y2ZOTpr4` or `https://www.youtube.com/watch?v=mQ-y2ZOTpr4`
- `language` (query): Language code (default: `en`)
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

**Example:**
```bash
curl "http://localhost:8000/api/v1/youtube/transcript/mQ-y2ZOTpr4?language=en"
```

### 3. Get Transcript with Full Metadata

```bash
GET /api/v1/youtube/transcript/raw/{video_id}?language=en&use_cache=true
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
curl "http://localhost:8000/api/v1/youtube/transcript/raw/mQ-y2ZOTpr4?language=en"
```

### 4. Root Endpoint

```bash
GET /
```

Returns API information and available endpoints.

## Behavior

### Language Fallback

When a requested language is unavailable, the API automatically falls back to the first available transcript:
- Request: `language=pl` (Polish not available)
- Response: `language=<actual_language>` with available transcript (e.g., `en`, `de`, `pl`, etc.)
- Cache: Stored as `video_id_<actual_language>.json`
- Prioritizes: Manual transcripts over auto-generated ones

### Cache Logic

1. First checks cache for requested language (e.g., `pl`)
2. If not in cache: Fetches from YouTube with automatic language fallback
3. Saves to cache using the actual language returned by YouTube
4. Next request: Returns cached data with `cache_used: true`

## Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## MCP Server

MCP (Model Context Protocol) server is integrated with FastAPI and supports **StreamableHttpTransport** (recommended for production).

- **MCP Endpoint**: `http://localhost:8000/api/v1/mcp`
- **Transport**: StreamableHttpTransport (efficient bidirectional streaming over HTTP)
- **Tools**:
  - `get_youtube_transcript` - Fetch transcript with basic metadata from YouTube video
  - `clear_cache` - Clear cached transcript for a specific video

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

# ======================
# FUNCTIONALITY
# ======================
_APP_DEFAULT_LANGUAGE=en                  # Default language code (default: en)
_APP_USE_CACHE_DEFAULT=true               # Enable caching by default (default: true)

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
│   └── transcript.py     # API endpoints (transcript, raw, health)
├── services/
│   ├── cache_service.py   # Cache management (read, write, TTL)
│   └── youtube_service.py # YouTube integration (yt-dlp)
└── mcp/
    └── server.py          # MCP server with tools
```

## Development

### Project Status

Current version: 1.0.0

All features implemented:
- ✅ Cache service (init, read, write, size tracking, TTL)
- ✅ YouTube service (fetch transcript, full metadata, language fallback)
- ✅ API endpoints (transcript, raw, health)
- ✅ Rate limiting (30 req/min default)
- ✅ Docker configuration
- ✅ MCP server integration (2 tools)
- ✅ API key authentication (optional)
- ✅ Environment variables with `_APP_` prefix
- ✅ Full Swagger/OpenAPI documentation

## Cache Structure

Cache files are stored as JSON:
```
cache/
├── {video_id}_{language}.json
└── qrxI6gBn3YE_en.json
```

Each cache file contains:
- `video_id` - YouTube video ID
- `transcript` - Full transcript text
- `language` - Actual language code
- `cache_used` - Always `true` when loaded from cache
- `cached_at` - ISO timestamp when cached
- `metadata` - Full yt-dlp metadata (all fields)

## License

MIT
