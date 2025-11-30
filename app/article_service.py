"""Article content extraction service."""

import re
import httpx
from bs4 import BeautifulSoup
from typing import Optional


def is_article_url(url: str) -> bool:
    """
    Check if URL is likely an article (not YouTube, podcast, or direct audio).
    This is a fallback check - if it's not a known media type, treat as article.
    """
    url_lower = url.lower()

    # Exclude known media types
    media_patterns = [
        "youtube.com", "youtu.be",
        "podcasts.apple.com",
        ".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".mp4", ".m4b"
    ]

    return not any(pattern in url_lower for pattern in media_patterns)


def is_audio_url(url: str) -> bool:
    """Check if URL points to a direct audio file."""
    url_lower = url.lower()
    audio_extensions = [".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".mp4", ".m4b"]
    return any(ext in url_lower for ext in audio_extensions)


async def fetch_article_content(url: str) -> dict:
    """
    Fetch and extract text content from an article URL.

    Args:
        url: Article URL to fetch

    Returns:
        dict with 'title' and 'transcript' (article content) keys
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = None
    if soup.title:
        title = soup.title.string
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content")
    title = title or "Untitled Article"

    # Remove unwanted elements
    for element in soup(["script", "style", "nav", "header", "footer", "aside",
                         "form", "button", "iframe", "noscript"]):
        element.decompose()

    # Try to find main content area
    main_content = None

    # Common content selectors
    content_selectors = [
        "article",
        "[role='main']",
        "main",
        ".post-content",
        ".article-content",
        ".entry-content",
        ".content",
        "#content",
        ".post",
        ".article",
    ]

    for selector in content_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break

    # Fallback to body
    if not main_content:
        main_content = soup.body or soup

    # Extract text
    text = main_content.get_text(separator="\n", strip=True)

    # Clean up whitespace
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)

    # Join with double newlines for paragraph separation
    content = "\n\n".join(lines)

    # Remove excessive whitespace
    content = re.sub(r"\n{3,}", "\n\n", content)

    return {
        "title": title.strip(),
        "transcript": content,
    }
