#!/usr/bin/env python3
"""
Convert VTT subtitle file to plain text without timestamps.
"""

import re
import sys
from pathlib import Path


def vtt_to_text(vtt_file: str, output_file: str = None) -> str:
    """
    Convert VTT file to plain text without timestamps.
    
    Args:
        vtt_file: Path to VTT file
        output_file: Output text file path (optional)
    
    Returns:
        Plain text content
    """
    vtt_path = Path(vtt_file)
    if not vtt_path.exists():
        raise FileNotFoundError(f"VTT file not found: {vtt_file}")
    
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    clean_segments = []
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        
        if '-->' in line or line.startswith('align:'):
            continue
        
        if '<' in line and '>' in line:
            continue
        
        if line and not line.startswith('<'):
            clean_segments.append(line)
    
    seen = set()
    unique_segments = []
    prev_seg = ""
    
    for seg in clean_segments:
        seg_normalized = re.sub(r'\s+', ' ', seg).strip()
        if not seg_normalized:
            continue
        
        if seg_normalized == prev_seg:
            continue
        
        if seg_normalized.startswith(prev_seg) and len(seg_normalized) > len(prev_seg):
            prev_seg = seg_normalized
            if unique_segments:
                unique_segments[-1] = seg_normalized
            else:
                unique_segments.append(seg_normalized)
            continue
        
        if prev_seg and seg_normalized.startswith(prev_seg):
            continue
        
        if seg_normalized not in seen:
            seen.add(seg_normalized)
            unique_segments.append(seg_normalized)
            prev_seg = seg_normalized
    
    text = ' '.join(unique_segments)
    
    text = re.sub(r'\.\s+([A-Z])', r'.\n\1', text)
    text = re.sub(r'!\s+([A-Z])', r'!\n\1', text)
    text = re.sub(r'\?\s+([A-Z])', r'?\n\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    if output_file:
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Text saved to: {output_path}")
    
    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python vtt_to_text.py <vtt_file> [output_file]")
        sys.exit(1)
    
    vtt_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if output_file is None:
        vtt_path = Path(vtt_file)
        output_file = vtt_path.stem + "_no_timestamps.txt"
    
    try:
        vtt_to_text(vtt_file, output_file)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

