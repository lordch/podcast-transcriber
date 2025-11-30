"""Content type detection utilities."""

import re
from typing import Optional


def detect_content_type(url: str) -> str:
    """
    Auto-detect content type from URL.

    Args:
        url: The URL to analyze

    Returns:
        Content type: "YouTube", "Podcast", or "Article"
    """
    url_lower = url.lower()

    # YouTube
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"

    # Apple Podcasts
    if "podcasts.apple.com" in url_lower:
        return "Podcast"

    # Direct audio files
    audio_extensions = [".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".mp4", ".m4b"]
    if any(ext in url_lower for ext in audio_extensions):
        return "Podcast"

    # Default to article
    return "Article"


def extract_url_from_text(text: str) -> Optional[str]:
    """
    Extract URL from text that might contain a URL.

    Handles cases where URL is in title field or mixed with other text.

    Args:
        text: Text that might contain a URL

    Returns:
        Extracted URL or None
    """
    if not text:
        return None

    text = text.strip()

    # If the whole text is a URL
    if text.startswith("http://") or text.startswith("https://"):
        # Extract just the URL part (in case there's trailing text)
        match = re.match(r"(https?://[^\s]+)", text)
        if match:
            return match.group(1)

    # Try to find URL anywhere in text
    url_pattern = r"https?://[^\s]+"
    match = re.search(url_pattern, text)
    if match:
        return match.group(0)

    return None


def find_content_url(url_field: Optional[str], title_field: Optional[str]) -> Optional[str]:
    """
    Find the content URL from either the URL field or Title field.

    When sharing to Notion, the URL can end up in either field depending
    on the sharing method used.

    Args:
        url_field: Value from the URL property
        title_field: Value from the Name/Title property

    Returns:
        The content URL, or None if not found
    """
    # Priority 1: Check URL field
    if url_field:
        url = extract_url_from_text(url_field)
        if url:
            return url

    # Priority 2: Check Title field
    if title_field:
        url = extract_url_from_text(title_field)
        if url:
            return url

    return None
