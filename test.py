#!/usr/bin/env python3
"""Test script for YouTube metadata fetching"""

import sys

def test_yt_dlp():
    """Test yt-dlp metadata fetching"""
    try:
        import yt_dlp
        video_id = "9Wg6tiaar9M"
        url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"Testing yt-dlp for: {url}")
        print("-" * 50)

        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)

        print(f"✅ Title: {info.get('title')}")
        print(f"✅ Author: {info.get('uploader')}")
        print(f"✅ Length: {info.get('duration')} seconds")
        print(f"✅ Views: {info.get('view_count')}")
        print(f"✅ Upload Date: {info.get('upload_date')}")
        print(f"✅ Description: {info.get('description', 'N/A')[:100]}...")

        return True
    except Exception as e:
        print(f"❌ yt-dlp error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_youtube_transcript_api():
    """Test youtube-transcript-api"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = "9Wg6tiaar9M"
        print(f"\nTesting youtube-transcript-api for: {video_id}")
        print("-" * 50)

        # Create API instance
        api = YouTubeTranscriptApi()

        # Get transcript using fetch (not get_transcript)
        transcript_list = api.fetch(video_id, languages=['pl'])

        print(f"✅ Got {len(list(transcript_list))} transcript segments")

        # Convert to list to check
        transcript_list = list(transcript_list)
        print(f"✅ First segment: {transcript_list[0]}")

        return True
    except Exception as e:
        print(f"❌ Transcript API error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_youtube_transcript_api_en():
    """Test youtube-transcript-api with English"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = "9Wg6tiaar9M"
        print(f"\nTesting youtube-transcript-api (EN) for: {video_id}")
        print("-" * 50)

        # Create API instance
        api = YouTubeTranscriptApi()

        # Get transcript using fetch with English
        transcript_list = api.fetch(video_id, languages=['en'])

        # Convert to list
        transcript_list = list(transcript_list)
        print(f"✅ Got {len(transcript_list)} transcript segments")
        print(f"✅ First segment: {transcript_list[0]}")

        return True
    except Exception as e:
        print(f"❌ Transcript API error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("YouTube API Tests\n")

    # Test yt-dlp
    yt_dlp_ok = test_yt_dlp()

    # Test transcript API with English (no Polish)
    print("\n")
    transcript_ok = test_youtube_transcript_api_en()

    print("\n" + "=" * 50)
    print("Results:")
    print(f"  yt-dlp: {'✅ OK' if yt_dlp_ok else '❌ FAIL'}")
    print(f"  Transcript API (en): {'✅ OK' if transcript_ok else '❌ FAIL'}")

    sys.exit(0 if (yt_dlp_ok and transcript_ok) else 1)
