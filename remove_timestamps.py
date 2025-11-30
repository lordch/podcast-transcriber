#!/usr/bin/env python3
"""
Remove timestamps from transcription file.
Processes the existing transcription.txt and creates a clean version without timestamps.
"""

import argparse
import re
import sys


def remove_timestamps(input_file: str, output_file: str = None) -> str:
    """
    Remove timestamp patterns from transcription file.
    
    Timestamp format: [X.XXs -> Y.YYs] at the start of each line
    """
    if output_file is None:
        output_file = input_file.replace(".txt", "_no_timestamps.txt")
        if output_file == input_file:
            output_file = "transcription_no_timestamps.txt"
    
    timestamp_pattern = re.compile(r'^\[\d+\.\d+s\s*->\s*\d+\.\d+s\]\s*')
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        cleaned_lines = []
        for line in lines:
            cleaned_line = timestamp_pattern.sub("", line)
            cleaned_lines.append(cleaned_line)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.writelines(cleaned_lines)
        
        print(f"Removed timestamps from {input_file}")
        print(f"Saved clean transcription to: {output_file}")
        return output_file
        
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Remove timestamps from transcription file"
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default="transcription.txt",
        help="Input transcription file (default: transcription.txt)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file (default: input_file with '_no_timestamps' suffix)",
    )
    
    args = parser.parse_args()
    
    remove_timestamps(args.input_file, args.output)


if __name__ == "__main__":
    main()


