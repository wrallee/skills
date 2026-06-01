#!/home/wrallee/.hermes/hermes-agent/venv/bin/python3
"""Extract or merge voices from a MusicXML (.mxl) file using music21.

Usage:
    # List all parts and their voices
    python3 extract_voice.py input.mxl --list

    # Extract only Voice 1 from a specific part into a new .mxl
    python3 extract_voice.py input.mxl --part P1 --voice 1 --out voice1.mxl

    # Merge all voices in a part into a single voice stream
    python3 extract_voice.py input.mxl --part P1 --merge --out merged.mxl

    # Merge all voices, all parts
    python3 extract_voice.py input.mxl --merge-all --out flat.mxl
"""

import argparse
import sys

from music21 import converter


def list_structure(score):
    """Print part and voice structure."""
    for part in score.parts:
        pid = part.id if hasattr(part, 'id') else "?"
        pname = part.partName or "(unnamed)"
        voices = set()
        for m in part.getElementsByClass('Measure'):
            for v in m.voices:
                voices.add(v.id)
        voice_str = ", ".join(sorted(voices)) if voices else "single"
        print(f"{pid} ({pname}): {voice_str}")


def merge_voices_in_part(part):
    """Merge all voices in each measure into a single flat stream by offset order."""
    for m in part.getElementsByClass('Measure'):
        if not m.voices:
            continue

        # Collect all notes/rests from all voices, sorted by offset
        all_events = []
        for v in m.voices:
            all_events.extend(v.notesAndRests)
        all_events.sort(key=lambda e: (e.offset, e.priority if hasattr(e, 'priority') else 0))

        # Keep non-voice elements (barlines, clefs, key sigs, etc.)
        non_voice = [el for el in m.elements if el.classes[0] != 'Voice']
        m.elements = tuple(non_voice)
        for event in all_events:
            m.append(event)

    return part


def extract_voice_from_part(part, voice_id):
    """Keep only notes with the specified voice ID, remove other voices."""
    for m in part.getElementsByClass('Measure'):
        if not m.voices:
            continue

        target = None
        for v in m.voices:
            if v.id == voice_id:
                target = v
                break

        if target is None:
            continue

        non_voice = [el for el in m.elements if el.classes[0] != 'Voice']
        m.elements = tuple(non_voice)
        for event in target.notesAndRests:
            m.append(event)

    return part


def main():
    parser = argparse.ArgumentParser(description="Extract or merge voices in MusicXML (music21)")
    parser.add_argument("mxl_path", help="Path to input .mxl file")
    parser.add_argument("--list", action="store_true", help="List parts and voices")
    parser.add_argument("--part", help="Target part ID (e.g., P1)")
    parser.add_argument("--voice", help="Voice ID to extract (e.g., '1')")
    parser.add_argument("--merge", action="store_true", help="Merge all voices in target part")
    parser.add_argument("--merge-all", action="store_true", help="Merge voices in ALL parts")
    parser.add_argument("--out", help="Output .mxl path")
    args = parser.parse_args()

    score = converter.parse(args.mxl_path)

    if args.list:
        list_structure(score)
        return

    if args.merge_all:
        for part in score.parts:
            merge_voices_in_part(part)
        action = "merged_all"
    elif args.part is not None:
        # Accept index (0-based) or part ID
        target = None
        try:
            idx = int(args.part)
            target = score.parts[idx]
        except ValueError:
            for part in score.parts:
                pid = part.id if hasattr(part, 'id') else None
                if pid == args.part:
                    target = part
                    break
        if target is None:
            print(f"ERROR: Part '{args.part}' not found", file=sys.stderr)
            sys.exit(1)

        if args.merge:
            merge_voices_in_part(target)
            action = f"{args.part}_merged"
        elif args.voice:
            extract_voice_from_part(target, args.voice)
            action = f"{args.part}_voice{args.voice}"
        else:
            print("ERROR: specify --merge or --voice", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: --part is required (use --list to see part IDs)", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or args.mxl_path.replace('.mxl', f'_{action}.mxl')
    score.write('musicxml', out_path)
    print(f"Done → {out_path}")


if __name__ == "__main__":
    main()
