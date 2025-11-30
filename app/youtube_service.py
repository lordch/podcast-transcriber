"""YouTube transcript service using yt-dlp."""

import re
import tempfile
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL


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
    Download transcript from YouTube video.

    Args:
        url: YouTube video URL
        language: Language code for subtitles

    Returns:
        dict with 'title' and 'transcript' keys
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Could not extract video ID from URL: {url}")

    with tempfile.TemporaryDirectory() as temp_dir:
        output_template = str(Path(temp_dir) / "%(title)s.%(ext)s")

        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [language, "en"],  # Fallback to English
            "subtitlesformat": "vtt",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": output_template,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown Title")

            # Find the downloaded subtitle file
            subtitle_file = None
            temp_path = Path(temp_dir)

            for ext in ["vtt", "srt", "json3"]:
                files = list(temp_path.glob(f"*.{ext}"))
                if files:
                    subtitle_file = files[0]
                    break

            if not subtitle_file:
                # Check for auto-generated subtitles
                available_subs = info.get("subtitles", {})
                auto_subs = info.get("automatic_captions", {})

                if not available_subs and not auto_subs:
                    raise ValueError("No subtitles available for this video")

                raise ValueError(
                    f"Subtitles exist but download failed. Available: {list(available_subs.keys()) + list(auto_subs.keys())}"
                )

            # Parse the subtitle file
            transcript = parse_vtt_file(subtitle_file)

            return {"title": title, "transcript": transcript, "video_id": video_id}


def parse_vtt_file(file_path: Path) -> str:
    """Parse VTT file and extract plain text transcript."""
    content = file_path.read_text(encoding="utf-8")

    # Remove VTT header
    lines = content.split("\n")
    text_lines = []
    skip_next = False

    for line in lines:
        line = line.strip()

        # Skip WEBVTT header and metadata
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue

        # Skip timestamp lines (e.g., "00:00:00.000 --> 00:00:02.000")
        if "-->" in line:
            skip_next = False
            continue

        # Skip cue identifiers (numeric lines before timestamps)
        if line.isdigit():
            continue

        # Skip empty lines
        if not line:
            continue

        # Remove VTT formatting tags like <c>, </c>, <00:00:00.000>
        clean_line = re.sub(r"<[^>]+>", "", line)
        clean_line = clean_line.strip()

        if clean_line and clean_line not in text_lines[-1:]:
            text_lines.append(clean_line)

    # Join and clean up the transcript
    transcript = " ".join(text_lines)

    # Remove duplicate phrases that often appear in auto-generated subtitles
    transcript = re.sub(r"(\b\w+\b)( \1)+", r"\1", transcript)

    return transcript
