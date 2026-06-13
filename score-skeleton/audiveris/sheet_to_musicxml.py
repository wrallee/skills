#!/usr/bin/env python3
"""sheet_to_musicxml.py — Audiveris LINKS-step sheet#1.xml → MusicXML.

Extracts clef, key signature, time signature, and measure structure
from Audiveris .omr intermediate data (pre-RHYTHMS, pre-MeasureFixer).
Outputs uncompressed .musicxml with placeholder rests.

Usage:
  python3 sheet_to_musicxml.py <song>/_audiveris/page-N.omr [--output out.musicxml]
"""

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from collections import defaultdict

MUSICXML_NS = ""


def xml_el(tag, attrib=None, text=None, **extra):
    """Create a MusicXML element."""
    el = ET.Element(tag, attrib=(attrib or {}))
    if text is not None:
        el.text = str(text)
    for k, v in extra.items():
        el.set(k.replace("_", "-"), str(v))
    return el


def sub_el(parent, tag, attrib=None, text=None, **extra):
    el = ET.SubElement(parent, tag, attrib=(attrib or {}))
    if text is not None:
        el.text = str(text)
    for k, v in extra.items():
        el.set(k.replace("_", "-"), str(v))
    return el


def load_omr(omr_path):
    """Load .omr zip, return (book_xml_root, sheet_xml_root, sheet_name)."""
    with zipfile.ZipFile(omr_path, "r") as zf:
        # Find sheet XML
        sheet_names = [n for n in zf.namelist() if "sheet#" in n and n.endswith(".xml") and "/" in n]
        if not sheet_names:
            raise FileNotFoundError("No sheet#N/sheet#N.xml found in .omr")

        sheet_name = sheet_names[0]
        sheet_root = ET.fromstring(zf.read(sheet_name))

        book_bytes = zf.read("book.xml") if "book.xml" in zf.namelist() else None
        book_root = ET.fromstring(book_bytes) if book_bytes else None

    return book_root, sheet_root, sheet_name


def build_id_map(sheet_root):
    """Build id → element dict from sheet XML."""
    by_id = {}
    for el in sheet_root.iter():
        sid = el.get("id")
        if sid:
            by_id[sid] = el
    return by_id


def resolve(el, by_id):
    """Resolve a reference element: if text is an ID, return the target element."""
    if el is None:
        return None
    ref_id = (el.text or "").strip()
    return by_id.get(ref_id)


def extract_measure_data(sheet_root, by_id):
    """Extract per-system, per-part, per-staff measure/header data."""
    page = sheet_root.find("page")
    if page is None:
        raise ValueError("No <page> element in sheet XML")

    systems_data = []

    for system in page.findall("system"):
        sys_data = {"parts": []}

        for part in system.findall("part"):
            part_data = {"staves": [], "measures": []}

            # Staff-level headers
            for staff in part.findall("staff"):
                staff_data = {}
                hdr = staff.find("header")
                if hdr is not None:
                    clef_el = hdr.find("clef")
                    key_el = hdr.find("key")
                    time_el = hdr.find("time")

                    clef_obj = resolve(clef_el, by_id)
                    key_obj = resolve(key_el, by_id)
                    time_obj = resolve(time_el, by_id)

                    if clef_obj is not None:
                        staff_data["clef_shape"] = clef_obj.get("shape", "")
                        staff_data["clef_pitch"] = clef_obj.get("pitch", "")
                        staff_data["clef_grade"] = clef_obj.get("ctx-grade", "")

                    if key_obj is not None:
                        staff_data["key_fifths"] = int(key_obj.get("fifths", 0))
                        staff_data["key_grade"] = key_obj.get("ctx-grade", "")

                    if time_obj is not None:
                        tr = time_obj.get("time-rational", "4/4")
                        parts = tr.split("/")
                        staff_data["time_beats"] = int(parts[0]) if len(parts) > 0 else 4
                        staff_data["time_beat_type"] = int(parts[1]) if len(parts) > 1 else 4
                        staff_data["time_shape"] = time_obj.get("shape", "")
                        staff_data["time_grade"] = time_obj.get("ctx-grade", "")
                else:
                    staff_data = {
                        "clef_shape": "", "key_fifths": 0,
                        "time_beats": 4, "time_beat_type": 4,
                    }

                part_data["staves"].append(staff_data)

            # Measure-level data
            for measure in part.findall("measure"):
                m_data = {
                    "clef_ids": [],
                    "key_ids": [],
                    "head_chord_ids": [],
                    "rest_chord_ids": [],
                    "head_chord_count": 0,
                    "rest_chord_count": 0,
                }

                for child in measure:
                    ids = (child.text or "").strip().split()
                    if child.tag == "clefs":
                        m_data["clef_ids"] = ids
                    elif child.tag == "keys":
                        m_data["key_ids"] = ids
                    elif child.tag == "head-chords":
                        m_data["head_chord_ids"] = ids
                        m_data["head_chord_count"] = len(ids)
                    elif child.tag == "rest-chords":
                        m_data["rest_chord_ids"] = ids
                        m_data["rest_chord_count"] = len(ids)

                part_data["measures"].append(m_data)

            # Left barline info
            left_bar = part.find("left-barline")
            if left_bar is not None:
                part_data["left_barline"] = True

            sys_data["parts"].append(part_data)

        systems_data.append(sys_data)

    return systems_data


def build_musicxml(systems_data, divisions=10080):
    """Build MusicXML partwise score from extracted data."""
    score = ET.Element("score-partwise", version="4.0")

    # --- work ---
    work = sub_el(score, "work")
    sub_el(work, "work-title", text="Score Skeleton")

    # --- part-list ---
    part_list = sub_el(score, "part-list")
    num_parts = max((len(s["parts"]) for s in systems_data), default=1)
    for pidx in range(1, num_parts + 1):
        sp = sub_el(part_list, "score-part", id=f"P{pidx}")
        sub_el(sp, "part-name", text=f"Part {pidx}")

    # --- parts ---
    for pidx in range(num_parts):
        part_el = ET.SubElement(score, "part", id=f"P{pidx+1}")
        measure_num = 0

        for sys_idx, sys_data in enumerate(systems_data):
            parts = sys_data["parts"]
            if pidx >= len(parts):
                continue
            part_data = parts[pidx]
            measures = part_data["measures"]

            # Pick best header from staves
            staves = part_data["staves"]
            if staves:
                hdr = staves[0]
            else:
                hdr = {"clef_shape": "", "key_fifths": 0, "time_beats": 4, "time_beat_type": 4}

            for m_data in measures:
                measure_num += 1
                meas_el = ET.SubElement(part_el, "measure", number=str(measure_num))

                # Attributes (only for first measure of each system, or when key/clef change)
                is_first_in_system = (m_data is measures[0])
                is_first_overall = (sys_idx == 0 and is_first_in_system)

                if is_first_in_system or is_first_overall:
                    attr_el = sub_el(meas_el, "attributes")
                    sub_el(attr_el, "divisions", text=str(divisions))

                    # Key
                    key_fifths = hdr.get("key_fifths", 0)
                    key_el = sub_el(attr_el, "key")
                    sub_el(key_el, "fifths", text=str(key_fifths))

                    # Time
                    tb = hdr.get("time_beats", 4)
                    tbt = hdr.get("time_beat_type", 4)
                    time_el = sub_el(attr_el, "time")
                    sub_el(time_el, "beats", text=str(tb))
                    sub_el(time_el, "beat-type", text=str(tbt))

                    # Clef
                    clef_shape = hdr.get("clef_shape", "")
                    clef_el = sub_el(attr_el, "clef")
                    if "G_CLEF" in clef_shape or "TREBLE" in clef_shape.upper():
                        sub_el(clef_el, "sign", text="G")
                        sub_el(clef_el, "line", text="2")
                    elif "F_CLEF" in clef_shape or "BASS" in clef_shape.upper():
                        sub_el(clef_el, "sign", text="F")
                        sub_el(clef_el, "line", text="4")
                    elif "C_CLEF" in clef_shape:
                        sub_el(clef_el, "sign", text="C")
                        sub_el(clef_el, "line", text="3")
                    else:
                        # Unknown — default to treble
                        sub_el(clef_el, "sign", text="G")
                        sub_el(clef_el, "line", text="2")

                # Placeholder note (whole rest) per measure
                tb_val = hdr.get("time_beats", 4)
                total_ticks = divisions * tb_val
                note_el = sub_el(meas_el, "note")
                sub_el(note_el, "rest")
                sub_el(note_el, "duration", text=str(total_ticks))
                sub_el(note_el, "type", text="whole")
                sub_el(note_el, "voice", text="1")

    return score


def main():
    if len(sys.argv) < 2:
        print("Usage: sheet_to_musicxml.py <page-N.omr> [--output out.musicxml]")
        sys.exit(1)

    omr_path = Path(sys.argv[1])
    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[idx + 1])
    if output_path is None:
        output_path = omr_path.with_suffix(".musicxml")

    print(f"Loading {omr_path}...")
    book_root, sheet_root, sheet_name = load_omr(omr_path)
    print(f"  Sheet: {sheet_name}")

    print("Building ID map...")
    by_id = build_id_map(sheet_root)
    print(f"  {len(by_id)} elements indexed")

    print("Extracting measure data...")
    systems_data = extract_measure_data(sheet_root, by_id)

    for si, sd in enumerate(systems_data):
        for pi, pd in enumerate(sd["parts"]):
            hdr = pd["staves"][0] if pd["staves"] else {}
            clef = hdr.get("clef_shape", "?")
            key_f = hdr.get("key_fifths", "?")
            time_s = f"{hdr.get('time_beats', '?')}/{hdr.get('time_beat_type', '?')}"
            n_meas = len(pd["measures"])
            print(f"  S{si} P{pi}: clef={clef} key=fifths={key_f} time={time_s} measures={n_meas}")

    print("Building MusicXML...")
    score_el = build_musicxml(systems_data)

    tree = ET.ElementTree(score_el)
    ET.indent(tree, space="  ")
    tree.write(str(output_path), encoding="utf-8", xml_declaration=True)
    print(f"Written: {output_path}")


if __name__ == "__main__":
    main()
