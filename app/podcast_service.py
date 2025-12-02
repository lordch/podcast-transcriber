"""Apple Podcast transcription service using Whisper API."""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET

import httpx
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Max size for Whisper API (25MB, use 24MB to be safe)
MAX_CHUNK_SIZE_MB = 24
# Target chunk duration in seconds (10 minutes)
CHUNK_DURATION_SECONDS = 600


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


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def split_audio_file(input_path: str, output_dir: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> list[str]:
    """
    Split audio file into chunks using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_dir: Directory to save chunks
        chunk_duration: Duration of each chunk in seconds

    Returns:
        List of paths to chunk files
    """
    duration = get_audio_duration(input_path)
    num_chunks = int(duration / chunk_duration) + 1

    chunk_paths = []

    for i in range(num_chunks):
        start_time = i * chunk_duration
        output_path = os.path.join(output_dir, f"chunk_{i:03d}.mp3")

        # Use ffmpeg to extract chunk
        subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite output
                "-i", input_path,
                "-ss", str(start_time),
                "-t", str(chunk_duration),
                "-acodec", "libmp3lame",
                "-ab", "64k",  # Lower bitrate to reduce file size
                "-ar", "16000",  # 16kHz sample rate (good for speech)
                "-ac", "1",  # Mono
                output_path,
            ],
            capture_output=True,
            check=True,
        )

        # Only add if file was created and has content
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            chunk_paths.append(output_path)

    return chunk_paths


async def transcribe_audio_chunk(client: AsyncOpenAI, chunk_path: str) -> str:
    """Transcribe a single audio chunk."""
    with open(chunk_path, "rb") as f:
        audio_content = f.read()

    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=("chunk.mp3", audio_content),
        response_format="text",
    )

    return transcript


async def transcribe_with_chunking(audio_content: bytes, file_ext: str = "mp3") -> str:
    """
    Transcribe large audio file by splitting into chunks.

    Args:
        audio_content: Raw audio file bytes
        file_ext: Audio file extension

    Returns:
        Combined transcript text
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Save original audio to temp file
        input_path = os.path.join(temp_dir, f"input.{file_ext}")
        with open(input_path, "wb") as f:
            f.write(audio_content)

        logger.info(f"Saved audio to {input_path}, size: {len(audio_content) / 1024 / 1024:.1f}MB")

        # Split into chunks
        logger.info("Splitting audio into chunks...")
        chunk_paths = split_audio_file(input_path, temp_dir)
        logger.info(f"Created {len(chunk_paths)} chunks")

        # Transcribe each chunk
        transcripts = []
        for i, chunk_path in enumerate(chunk_paths):
            chunk_size = os.path.getsize(chunk_path) / 1024 / 1024
            logger.info(f"Transcribing chunk {i + 1}/{len(chunk_paths)} ({chunk_size:.1f}MB)...")

            transcript = await transcribe_audio_chunk(client, chunk_path)
            transcripts.append(transcript)

        # Combine transcripts
        full_transcript = " ".join(transcripts)
        logger.info(f"Transcription complete. Total length: {len(full_transcript)} chars")

        return full_transcript


async def transcribe_podcast_audio(audio_url: str) -> str:
    """
    Transcribe podcast audio using OpenAI Whisper API.

    For files over 25MB, automatically chunks the audio using ffmpeg.

    Args:
        audio_url: Direct URL to the audio file (MP3, etc.)

    Returns:
        Transcript text
    """
    settings = get_settings()

    # Download audio file to memory
    logger.info(f"Downloading audio from {audio_url}")
    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as http_client:
        response = await http_client.get(audio_url)
        response.raise_for_status()
        audio_content = response.content

    # Check file size
    file_size_mb = len(audio_content) / (1024 * 1024)
    logger.info(f"Downloaded audio: {file_size_mb:.1f}MB")

    # Determine file extension from URL
    file_ext = "mp3"  # Default
    if ".m4a" in audio_url:
        file_ext = "m4a"
    elif ".wav" in audio_url:
        file_ext = "wav"
    elif ".ogg" in audio_url:
        file_ext = "ogg"

    if file_size_mb > MAX_CHUNK_SIZE_MB:
        # Use chunking for large files
        logger.info(f"File exceeds {MAX_CHUNK_SIZE_MB}MB, using chunked transcription")
        return await transcribe_with_chunking(audio_content, file_ext)

    # For smaller files, transcribe directly
    client = AsyncOpenAI(api_key=settings.openai_api_key)

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
