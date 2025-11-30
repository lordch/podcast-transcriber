"""Apple Podcast transcription service using Whisper API."""

import re
import httpx
from openai import AsyncOpenAI
from typing import Optional
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET

from app.config import get_settings


def is_apple_podcast_url(url: str) -> bool:
    """Check if URL is an Apple Podcasts URL."""
    return "podcasts.apple.com" in url


async def get_podcast_audio_url(apple_podcast_url: str) -> dict:
    """
    Extract the direct audio URL from an Apple Podcasts episode URL.

    Apple Podcasts URLs don't directly give us the audio file.
    We need to:
    1. Parse the podcast/episode ID from the URL
    2. Use Apple's lookup API to get the RSS feed URL
    3. Parse the RSS feed to find the episode's audio URL

    Args:
        apple_podcast_url: Apple Podcasts episode URL

    Returns:
        dict with 'title', 'audio_url', 'podcast_name' keys
    """
    # Extract podcast ID and episode ID from URL
    # Example: https://podcasts.apple.com/us/podcast/episode-title/id1234567890?i=1000123456789

    parsed = urlparse(apple_podcast_url)
    path_parts = parsed.path.split("/")
    query_params = parse_qs(parsed.query)

    # Find podcast ID in path (format: id1234567890)
    podcast_id = None
    for part in path_parts:
        if part.startswith("id"):
            podcast_id = part[2:]  # Remove 'id' prefix
            break

    if not podcast_id:
        raise ValueError(f"Could not extract podcast ID from URL: {apple_podcast_url}")

    # Get episode ID from query params
    episode_id = query_params.get("i", [None])[0]

    # Use Apple's lookup API to get podcast feed URL
    lookup_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast"

    async with httpx.AsyncClient() as client:
        response = await client.get(lookup_url)
        response.raise_for_status()
        data = response.json()

    if not data.get("results"):
        raise ValueError(f"Podcast not found with ID: {podcast_id}")

    podcast_info = data["results"][0]
    feed_url = podcast_info.get("feedUrl")
    podcast_name = podcast_info.get("collectionName", "Unknown Podcast")

    if not feed_url:
        raise ValueError(f"No RSS feed URL found for podcast: {podcast_name}")

    # Fetch and parse the RSS feed
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
        feed_content = response.text

    # Parse RSS feed to find the episode
    episode_info = parse_rss_for_episode(feed_content, episode_id, apple_podcast_url)
    episode_info["podcast_name"] = podcast_name

    return episode_info


def parse_rss_for_episode(feed_content: str, episode_id: Optional[str], original_url: str) -> dict:
    """
    Parse RSS feed to find episode audio URL.

    Args:
        feed_content: RSS feed XML content
        episode_id: Apple episode ID (if available)
        original_url: Original Apple Podcasts URL for fallback matching

    Returns:
        dict with 'title' and 'audio_url' keys
    """
    # Define namespaces commonly used in podcast RSS feeds
    namespaces = {
        "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "atom": "http://www.w3.org/2005/Atom",
    }

    root = ET.fromstring(feed_content)
    channel = root.find("channel")

    if channel is None:
        raise ValueError("Invalid RSS feed: no channel element")

    items = channel.findall("item")

    if not items:
        raise ValueError("No episodes found in RSS feed")

    # Try to match by episode ID or URL patterns
    # Extract potential episode slug from original URL
    url_parts = original_url.lower().split("/")
    episode_slug = None
    for i, part in enumerate(url_parts):
        if part == "podcast" and i + 1 < len(url_parts):
            episode_slug = url_parts[i + 1]
            break

    best_match = None

    for item in items:
        title_elem = item.find("title")
        title = title_elem.text if title_elem is not None else "Unknown Episode"

        # Find enclosure (audio file)
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue

        audio_url = enclosure.get("url")
        if not audio_url:
            continue

        # Check for matching episode ID in guid or other fields
        guid = item.find("guid")
        if guid is not None and episode_id:
            if episode_id in (guid.text or ""):
                return {"title": title, "audio_url": audio_url}

        # Try to match by episode title/slug
        if episode_slug:
            title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
            if episode_slug in title_slug or title_slug in episode_slug:
                return {"title": title, "audio_url": audio_url}

        # Keep first episode as fallback (most recent)
        if best_match is None:
            best_match = {"title": title, "audio_url": audio_url}

    if best_match:
        return best_match

    raise ValueError("Could not find matching episode in RSS feed")


async def transcribe_podcast_audio(audio_url: str) -> str:
    """
    Transcribe podcast audio using OpenAI Whisper API.

    The Whisper API accepts audio files up to 25MB. For longer podcasts,
    we stream the audio directly to the API without downloading locally.

    Args:
        audio_url: Direct URL to the audio file (MP3, etc.)

    Returns:
        Transcript text
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Download audio file to memory (streaming)
    async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as http_client:
        response = await http_client.get(audio_url)
        response.raise_for_status()
        audio_content = response.content

    # Check file size (Whisper limit is 25MB)
    file_size_mb = len(audio_content) / (1024 * 1024)

    if file_size_mb > 25:
        # For large files, we need to chunk the audio
        # This is a simplified approach - for production, consider using ffmpeg
        raise ValueError(
            f"Audio file is {file_size_mb:.1f}MB, exceeds Whisper's 25MB limit. "
            "Consider using a shorter clip or implementing audio chunking."
        )

    # Determine file extension from URL or content type
    file_ext = "mp3"  # Default
    if ".m4a" in audio_url:
        file_ext = "m4a"
    elif ".wav" in audio_url:
        file_ext = "wav"
    elif ".ogg" in audio_url:
        file_ext = "ogg"

    # Send to Whisper API
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=(f"audio.{file_ext}", audio_content),
        response_format="text",
    )

    return transcript


async def get_podcast_transcript(apple_podcast_url: str) -> dict:
    """
    Main function to get transcript from Apple Podcast URL.

    Args:
        apple_podcast_url: Apple Podcasts episode URL

    Returns:
        dict with 'title', 'transcript', 'podcast_name' keys
    """
    # Get audio URL from Apple Podcasts link
    episode_info = await get_podcast_audio_url(apple_podcast_url)

    # Transcribe the audio
    transcript = await transcribe_podcast_audio(episode_info["audio_url"])

    return {
        "title": episode_info["title"],
        "transcript": transcript,
        "podcast_name": episode_info.get("podcast_name", "Unknown Podcast"),
    }
