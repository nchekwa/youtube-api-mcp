import random
import time
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    yt_dlp = None


class YouTubeService:
    """Service for fetching YouTube video transcripts and metadata."""

    def __init__(self):
        """Initialize YouTube service."""
        self.api = YouTubeTranscriptApi()

    def get_video_id(self, url_or_id: str) -> str:
        """
        Extract video ID from URL or return if already an ID.

        Args:
            url_or_id: YouTube URL or video ID

        Returns:
            YouTube video ID (11 characters)

        Raises:
            ValueError: If URL/ID is invalid
        """
        # If it's already a video ID (11 characters)
        if len(url_or_id) == 11 and not any(c in url_or_id for c in ['/', '.', '?', '&']):
            return url_or_id

        # Extract from various URL formats
        import re
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/watch\?.*v=([^&\n?#]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url_or_id)
            if match:
                return match.group(1)

        raise ValueError(f"Invalid YouTube URL or ID: {url_or_id}")

    def fetch_transcript(self, video_id: str) -> dict:
        """
        Fetch transcript for a YouTube video (first available language).

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with transcript data including metadata

        Raises:
            ValueError: If video is invalid or transcript not available
        """
        def _is_transient_network_error(exc: BaseException) -> bool:
            seen = set()

            def _iter_chain(e: BaseException):
                cur = e
                while cur is not None and id(cur) not in seen:
                    seen.add(id(cur))
                    yield cur
                    cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)

            for cur in _iter_chain(exc):
                if isinstance(cur, (ConnectionResetError, TimeoutError)):
                    return True
                msg = str(cur)
                if "Connection reset by peer" in msg:
                    return True
                if "Connection aborted" in msg:
                    return True
                if "Read timed out" in msg:
                    return True
                if "Remote end closed connection" in msg:
                    return True
            return False

        attempts = 3
        base_delay_s = 0.5

        for attempt in range(1, attempts + 1):
            try:
                transcript_data = self.api.list(video_id)

                available = [t for t in transcript_data if not t.is_generated]
                if not available:
                    available = list(transcript_data)

                if not available:
                    raise ValueError(f"No transcript found for video {video_id}")

                first_transcript = available[0]
                transcript_list = first_transcript.fetch()
                language = first_transcript.language_code

                transcript_text = " ".join([entry.text for entry in transcript_list])

                metadata = self._get_video_metadata(video_id)

                return {
                    "video_id": video_id,
                    "transcript": transcript_text,
                    "language": language,
                    "cached": False,
                    "cached_at": None,
                    "metadata": metadata  # Store full metadata only
                }

            except TranscriptsDisabled:
                raise ValueError(f"Transcripts are disabled for video {video_id}")
            except NoTranscriptFound:
                raise ValueError(f"No transcript found for video {video_id}")
            except VideoUnavailable:
                raise ValueError(f"Video {video_id} is unavailable")
            except Exception as e:
                if attempt < attempts and _is_transient_network_error(e):
                    delay = base_delay_s * (2 ** (attempt - 1))
                    delay = delay * (1.0 + random.random() * 0.25)
                    time.sleep(delay)
                    continue
                raise ValueError(f"Error fetching transcript: {str(e)}")

    def _get_video_metadata(self, video_id: str) -> dict:
        """
        Fetch video metadata using yt-dlp.

        Args:
            video_id: YouTube video ID

        Returns:
            Dict with all available video metadata
        """
        if not YTDLP_AVAILABLE:
            return {}

        try:
            url = f"https://www.youtube.com/watch?v={video_id}"

            # Use yt-dlp to extract all metadata
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)

            # Extract all relevant metadata
            metadata = {
                "title": info.get('title', 'Unknown'),
                "author": info.get('uploader', 'Unknown'),
                "channel_url": info.get('channel_url', ''),
                "duration": info.get('duration', 0),
                "publish_date": info.get('upload_date', 'Unknown'),
                "upload_date": info.get('upload_date', 'Unknown'),
                "view_count": info.get('view_count', 0),
                "like_count": info.get('like_count', 0),
                "comment_count": info.get('comment_count', 0),
                "description": info.get('description', ''),
                "thumbnail": info.get('thumbnail', ''),
                "thumbnails": info.get('thumbnails', []),
                "categories": info.get('categories', []),
                "tags": info.get('tags', []),
                "availability": info.get('availability', ''),
                "live_status": info.get('live_status', ''),
                "playable_in_embed": info.get('playable_in_embed', True),
                "width": info.get('width', 0),
                "height": info.get('height', 0),
                "fps": info.get('fps', 0),
                "vcodec": info.get('vcodec', ''),
                "acodec": info.get('acodec', ''),
                "format": info.get('format', ''),
                "ext": info.get('ext', ''),
                "filesize": info.get('filesize', 0),
                "fulltitle": info.get('fulltitle', ''),
                "duration_string": info.get('duration_string', ''),
                "upload_date": info.get('upload_date', ''),
                "uploader_id": info.get('uploader_id', ''),
                "uploader": info.get('uploader', ''),
                "uploader_url": info.get('uploader_url', ''),
                "channel": info.get('channel', ''),
                "channel_id": info.get('channel_id', ''),
                "channel_follower_count": info.get('channel_follower_count', 0),
                "location": info.get('location', ''),
                "subtitles": info.get('subtitles', {}),
                "automatic_captions": info.get('automatic_captions', {}),
            }

            return metadata

        except Exception as e:
            # Return empty dict if metadata fetch fails
            print(f"Error fetching metadata: {e}")
            return {}
