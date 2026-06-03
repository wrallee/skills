# Beat Assignment from PaddleOCR Bounding Box x-Position

## Why

PaddleOCR returns a bounding box (bbox) for each detected text line. The bbox's x-coordinate tells you where in the crop the chord symbol sits. Normalizing this within the measure width gives a **relative position** (0.0 = left barline, 1.0 = right barline), which maps to a beat position better than hardcoded even spacing.

## Algorithm

```
measure_px = e['x1'] - e['x0']           // measure width in page pixels
chord_center_x = (bbox[0][0] + bbox[2][0]) / 2   // bbox horizontal center (crop-relative)
crop_x0 = max(0, e['x0'] - PAD_X)                 // crop left edge in page coords
chord_x_page = chord_center_x + crop_x0            // convert to page-relative
rel_x = (chord_x_page - e['x0']) / measure_px     // normalize 0..1

// Map to nearest valid beat grid for the time signature
valid_beats = beats_map.get(TIME_SIG, [1.0])
target_beat = valid_beats[0] + rel_x * (valid_beats[-1] - valid_beats[0])
beat = min(valid_beats, key=lambda b: abs(b - target_beat))
```

## beat maps by time signature

| Time sig | Valid beats | Range |
|----------|------------|-------|
| 4/4      | 1.0, 2.0, 3.0, 4.0 | 0..3 |
| 3/4      | 1.0, 2.0, 3.0       | 0..2 |
| 6/8      | 1.0, 4.0            | compound beats |
| other    | 1.0 by default; define explicit grid before production use | — |

## Edge cases

- **Multiple chords at same x**: PaddleOCR may return overlapping bboxes for adjacent chords. Deduplicate: same normalized text within 50px vertical → keep higher confidence.
- **Single chord in measure**: rel_x is still computed but the only valid beat is determined by the nearest downbeat. In practice, a single chord nearly always maps to beat 1.0.
- **Chord near right barline**: rel_x ≈ 1.0 → maps to beat 4.0 (4/4) or 3.0 (3/4). This is correct for final-beat chords.
- **Slash bass symbols (`/F`, `/E`)**: These appear as separate bbox entries. Same rel_x logic applies — they should map to the same beat as their parent chord. The code already merges adjacent slash chords with the preceding full chord.
- **Fallback (no valid bbox)**: If OCR returned text but bbox coordinates are missing/unreliable (e.g., vision fallback path), fall back to even spacing by chord count.
