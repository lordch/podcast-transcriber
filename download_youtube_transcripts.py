#!/usr/bin/env python3
"""
Download transcripts/subtitles from YouTube videos using yt-dlp.
No API key required - extracts subtitles directly from YouTube.
"""

import argparse
import os
import sys
from pathlib import Path

from yt_dlp import YoutubeDL


def download_transcript(url: str, output_dir: str = ".", format: str = "txt", language: str = None) -> str:
    """
    Download transcript/subtitle from YouTube video.
    
    Args:
        url: YouTube video URL
        output_dir: Directory to save transcript
        format: Output format ('txt', 'srt', 'vtt', 'json')
        language: Language code (e.g., 'en', 'pl'). If None, uses auto-generated or first available.
    
    Returns:
        Path to downloaded transcript file
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    ydl_opts = {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "skip_download": True,
        "quiet": False,
        "no_warnings": False,
    }
    
    if language:
        ydl_opts["subtitleslangs"] = [language]
    
    if format == "txt":
        output_template = str(output_dir / "%(title)s.%(ext)s")
        ydl_opts["outtmpl"] = output_template
    elif format == "srt":
        ydl_opts["subtitlesformat"] = "srt"
        output_template = str(output_dir / "%(title)s.%(ext)s")
        ydl_opts["outtmpl"] = output_template
    elif format == "vtt":
        ydl_opts["subtitlesformat"] = "vtt"
        output_template = str(output_dir / "%(title)s.%(ext)s")
        ydl_opts["outtmpl"] = output_template
    elif format == "json":
        ydl_opts["subtitlesformat"] = "json3"
        output_template = str(output_dir / "%(title)s.%(ext)s")
        ydl_opts["outtmpl"] = output_template
    
    print(f"Downloading transcript from: {url}")
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            
            available_subs = info.get("subtitles", {})
            auto_subs = info.get("automatic_captions", {})
            
            if available_subs or auto_subs:
                print(f"\nAvailable subtitle languages:")
                for lang in sorted(set(list(available_subs.keys()) + list(auto_subs.keys()))):
                    sub_type = "manual" if lang in available_subs else "auto"
                    print(f"  - {lang} ({sub_type})")
            
            subtitle_files = []
            for ext in ["srt", "vtt", "json", "txt"]:
                pattern = output_dir / f"{title}.{ext}"
                if pattern.exists():
                    subtitle_files.append(str(pattern))
            
            if subtitle_files:
                print(f"\nTranscript saved to: {subtitle_files[0]}")
                return subtitle_files[0]
            else:
                print("\nWarning: No subtitle file found. The video might not have subtitles available.")
                return None
                
    except Exception as e:
        print(f"Error downloading transcript: {e}", file=sys.stderr)
        if "No subtitles found" in str(e) or "subtitles" in str(e).lower():
            print("\nThis video may not have subtitles available.", file=sys.stderr)
            print("Try a different video or check if the video has captions enabled.", file=sys.stderr)
        raise


def list_available_languages(url: str):
    """List all available subtitle languages for a video."""
    ydl_opts = {
        "writesubtitles": False,
        "writeautomaticsub": False,
        "skip_download": True,
        "quiet": True,
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            available_subs = info.get("subtitles", {})
            auto_subs = info.get("automatic_captions", {})
            
            if not available_subs and not auto_subs:
                print("No subtitles available for this video.")
                return
            
            print("Available subtitle languages:")
            all_langs = sorted(set(list(available_subs.keys()) + list(auto_subs.keys())))
            
            for lang in all_langs:
                sub_type = "manual" if lang in available_subs else "auto"
                formats = available_subs.get(lang, auto_subs.get(lang, []))
                format_list = ", ".join([f.get("ext", "unknown") for f in formats])
                print(f"  {lang}: {sub_type} ({format_list})")
                
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Download transcripts/subtitles from YouTube videos (no API key required)"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output",
        "-o",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["txt", "srt", "vtt", "json"],
        default="txt",
        help="Output format (default: txt)",
    )
    parser.add_argument(
        "--language",
        "-l",
        help="Language code (e.g., 'en', 'pl'). If not specified, uses first available.",
    )
    parser.add_argument(
        "--list-languages",
        action="store_true",
        help="List available subtitle languages for the video and exit",
    )
    
    args = parser.parse_args()
    
    try:
        if args.list_languages:
            list_available_languages(args.url)
            return
        
        transcript_file = download_transcript(
            args.url,
            args.output,
            args.format,
            args.language
        )
        
        if transcript_file:
            print(f"\nSuccess! Transcript saved to: {transcript_file}")
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()



