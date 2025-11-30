#!/usr/bin/env python3
"""
Podcast transcription script using OpenAI Whisper API and yt-dlp.
Downloads audio from Apple Podcasts and transcribes it using OpenAI's API.
"""

import argparse
import os
import sys
import tempfile

from dotenv import load_dotenv
from openai import OpenAI
from yt_dlp import YoutubeDL

load_dotenv()


def download_podcast_audio(url: str, output_dir: str = None) -> tuple[str, dict]:
    """Download audio from podcast URL using yt-dlp. Returns (audio_file_path, info_dict)."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    
    output_path = os.path.join(output_dir, "%(title)s.%(ext)s")
    
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "192",
        }],
        "quiet": False,
        "no_warnings": False,
    }
    
    print(f"Downloading audio from: {url}")
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        audio_file = filename.rsplit(".", 1)[0] + ".wav"
        
        if not os.path.exists(audio_file):
            audio_file = filename
        
        duration = info.get("duration", 0)
        print(f"Downloaded audio to: {audio_file}")
        if duration:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            print(f"Audio duration: {minutes}m {seconds}s")
        
        return audio_file, info


def transcribe_audio(audio_path: str, output_file: str = None, response_format: str = "text") -> str:
    """Transcribe audio file using OpenAI Whisper API."""
    if output_file is None:
        if response_format == "json" or response_format == "verbose_json":
            output_file = "transcription.json"
        elif response_format == "srt":
            output_file = "transcription.srt"
        elif response_format == "vtt":
            output_file = "transcription.vtt"
        else:
            output_file = "transcription.txt"
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment. Please set it in .env file.")
    
    client = OpenAI(api_key=api_key)
    
    print(f"Transcribing audio using OpenAI Whisper API: {audio_path}")
    
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format=response_format
        )
    
    if response_format == "verbose_json":
        import json
        language = getattr(transcript, "language", "unknown")
        print(f"Detected language: {language}")
        transcription_content = json.dumps(transcript.model_dump(), indent=2)
    elif response_format == "json":
        import json
        transcription_content = json.dumps(transcript.model_dump(), indent=2)
    else:
        transcription_content = transcript
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(transcription_content)
    
    print(f"Transcription saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Transcribe a podcast episode using OpenAI Whisper API")
    parser.add_argument("url", help="Apple Podcasts URL")
    parser.add_argument(
        "--output",
        default="transcription.txt",
        help="Output file for transcription (default: transcription.txt)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "verbose_json", "srt", "vtt"],
        default="text",
        help="Response format (default: text)",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep downloaded audio file after transcription",
    )
    
    args = parser.parse_args()
    
    try:
        audio_file, info = download_podcast_audio(args.url)
        duration = info.get("duration", 0)
        
        if duration:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            print(f"\nAudio duration: {minutes}m {seconds}s")
            print("Using OpenAI Whisper API (whisper-1 model)")
            print("Note: Transcription time depends on API response time, typically 1-3 minutes for 1-hour audio\n")
        
        response_format = args.format
        if args.format == "text":
            response_format = "text"
        elif args.format in ["json", "verbose_json"]:
            response_format = args.format
        else:
            response_format = args.format
        
        transcription_file = transcribe_audio(audio_file, args.output, response_format)
        
        if not args.keep_audio:
            print(f"Removing temporary audio file: {audio_file}")
            os.remove(audio_file)
        
        print(f"\nTranscription complete! Output saved to: {transcription_file}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

