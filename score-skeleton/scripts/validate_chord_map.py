#!/usr/bin/env python3
"""Post-process chord results: remove lead-in measures before start_repeat,
re-number measures, and validate chord consistency.

Usage:
  python3 scripts/validate_chord_map.py <page_results.json>

Lead-in removal: if a measure at system start has right_type='start_repeat'
and LLM returned 'empty', remove it and shift following measures by 1.
"""
import json, sys, re

CHORD_RE = re.compile(r'^[A-G](#|b)?(m|M|maj|min|dim|aug|sus|add)?[0-9]*(/[A-G](#|b)?)?$')

def remove_lead_ins(chord_results, barlines_info):
    """Remove lead-in measures before system-start start_repeat barlines."""
    out = []
    shift = 0
    for item in sorted(chord_results, key=lambda x: x['measure']):
        mn = item['measure']
        # Check if this measure should be removed (lead-in)
        should_remove = False
        for bi in barlines_info:
            if bi['first_measure'] == mn and item.get('text', '').lower() in ('', 'empty'):
                should_remove = True
                shift += 1
                break
        if should_remove:
            continue
        item['measure'] = mn - shift
        out.append(item)
    return out

def validate(chord_results):
    issues = []
    for item in chord_results:
        text = item.get('text', '')
        if text and text.lower() not in ('empty', '') and not CHORD_RE.match(text):
            issues.append(f"M{item['measure']}: '{text}' fails CHORD_RE")
    return issues

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        with open(path) as f:
            data = json.load(f)
        issues = validate(data.get('results', data))
        if issues:
            print(f"Found {len(issues)} issues:")
            for i in issues:
                print(f"  {i}")
        else:
            print("All checks passed.")
    else:
        print("Usage: python3 validate_chord_map.py <results.json>")

if __name__ == '__main__':
    main()
