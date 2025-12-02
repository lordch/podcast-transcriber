"""YouTube transcript service using youtube-transcript-api."""

import re
from typing import Optional

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([^&\?/]+)",
        r"youtube\.com/shorts/([^&\?/]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube URL."""
    youtube_patterns = [
        r"youtube\.com",
        r"youtu\.be",
    ]
    return any(re.search(pattern, url) for pattern in youtube_patterns)


async def get_youtube_transcript(url: str, language: str = "en") -> dict:
    """
    Download transcript from YouTube video using youtube-transcript-api.

    Args:
        url: YouTube video URL
        language: Language code for subtitles

    Returns:
        dict with 'title' and 'transcript' keys
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {url}")

    try:
        # Create API instance and fetch transcript
        api = YouTubeTranscriptApi()

        # Try to get transcript in preferred language, fallback to English
        transcript_data = api.fetch(video_id, languages=[language, 'en'])

        # Combine all text segments
        text_parts = [entry.text for entry in transcript_data]
        full_transcript = ' '.join(text_parts)

        # Clean up the transcript
        full_transcript = re.sub(r'\n+', ' ', full_transcript)
        full_transcript = re.sub(r'\s+', ' ', full_transcript)
        full_transcript = full_transcript.strip()

        # Get video title via oembed API
        title = await get_video_title(video_id)

        return {"title": title, "transcript": full_transcript, "video_id": video_id}

    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this video")
    except VideoUnavailable:
        raise ValueError("Video is unavailable")
    except NoTranscriptFound:
        raise ValueError("No transcript found for this video")


async def get_video_title(video_id: str) -> str:
    """Get video title using oembed API (no authentication required)."""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get("title", f"YouTube Video {video_id}")
    except Exception:
        pass

    return f"YouTube Video {video_id}"
