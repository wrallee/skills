#!/home/wrallee/.hermes/hermes-agent/venv/bin/python3
"""Dump all note pitches from a MusicXML (.mxl) file by part and measure.

Usage:
    python3 dump_mxl_pitches.py <file.mxl> [--part P1] [--measure-range 1-20]
"""

import argparse
import zipfile
import xml.etree.ElementTree as ET
import sys


def main():
    parser = argparse.ArgumentParser(description="Dump pitches from MusicXML (.mxl)")
    parser.add_argument("mxl_path", help="Path to .mxl file")
    parser.add_argument("--part", help="Filter by part ID (e.g., P1)")
    parser.add_argument("--measure-range", help="Measure range (e.g., 1-20)")
    args = parser.parse_args()

    measure_start, measure_end = None, None
    if args.measure_range:
        parts = args.measure_range.split("-")
        measure_start = int(parts[0])
        measure_end = int(parts[1]) if len(parts) > 1 else measure_start

    with zipfile.ZipFile(args.mxl_path) as z:
        for name in z.namelist():
            if "META" not in name and name.endswith(".xml"):
                with z.open(name) as f:
                    tree = ET.parse(f)
                root = tree.getroot()

                for part in root.findall("part"):
                    pid = part.get("id")
                    if args.part and pid != args.part:
                        continue

                    for measure in part.findall("measure"):
                        mnum = int(measure.get("number"))
                        if measure_start and (mnum < measure_start or mnum > measure_end):
                            continue

                        notes = measure.findall("note")
                        pitches = []
                        for note in notes:
                            pitch = note.find("pitch")
                            rest = note.find("rest")
                            if pitch is not None:
                                step = pitch.find("step")
                                alter = pitch.find("alter")
                                octave = pitch.find("octave")
                                s = step.text if step is not None else "?"
                                a = "#" if alter is not None and alter.text == "1" else "b" if alter is not None and alter.text == "-1" else ""
                                o = octave.text if octave is not None else "?"
                                pitches.append(f"{s}{a}{o}")
                            elif rest is not None:
                                pitches.append("R")

                        if pitches:
                            pitch_str = " ".join(pitches[:16])
                            more = " ..." if len(pitches) > 16 else ""
                            print(f"{pid} m{mnum:>3}: {pitch_str}{more}")


if __name__ == "__main__":
    main()
