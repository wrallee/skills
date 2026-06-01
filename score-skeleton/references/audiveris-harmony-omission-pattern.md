# Audiveris Harmony Omission: Roller Coaster Case Study

## Score Profile

| Property | Value |
|---|---|
| Song | 이무진 — Roller Coaster |
| Source | Finale 2008 PDF |
| Measures | 82 |
| Expected chords | 93 (chord_map) |
| Audiveris detected | 42 harmonies (45%) |

## Chord Detection Breakdown

### Detected correctly (identity + measure match)
D, E, A, Bm, DM7 (`Dmajor-seventh`), Emajor, Amajor, Bm7

### Systematically omitted (no harmony element at all)
**F#m** — missing from every page despite appearing 22+ times in the score.
**C#m, C#7** — missing entirely.

### Root cause
Audiveris chord name classifier does not recognize `#` (sharp) in text tokens
as a valid chord modifier. Text "F#m" triggers the chord classifier? Audiveris
looks for root letter (F) plus optional accidental? The `#` symbol in the PDF
font either:
1. Is not recognized by Tesseract OCR as a sharp sign (#), or
2. The chord pattern matcher rejects tokens with `#` because it doesn't match
   the expected chord syntax (root letter + optional quality suffix)

### What Audiveris gets right
- **Measure assignment**: 35/42 detected chords (83%) had correct measure number
- **Chord identity**: When detected, root and quality are correct (E → Emajor,
  Bm → Bminor, D → Dmajor, DM7 → Dmajor-seventh)
- **Part assignment**: All 42 harmonies in Voice part (P1), not spilled into
  piano staves

### What Audiveris gets wrong/absent
- **Temporal offset**: Always `<offset>0</offset>` — no beat position info
- **F#m**: Entirely absent from all pages
- **C#m, C#7**: Entirely absent
- **Spurious misses**: Some simple chords (E at M2, M4, M6 on page 1) also
  omitted for unclear reasons (possibly interference from nearby Korean lyrics)

## Practical Implications for Step 7 Reconciliation

```
If Audiveris found "Dmajor" at measure N  →  treat as confirmed
If Audiveris found nothing at measure N   →  still check, especially for
                                             chords with # in root
If vision says F#m and Audiveris nothing  →  trust vision
```

## Extraction Method

```python
import zipfile, re

with zipfile.ZipFile('_scratch/links/source.mxl') as z:
    xml = z.read('source.xml').decode('utf-8')

# Find P1 specifically (Voice part)
p1_start = xml.find('<part id="P1"')
depth, p1_end = 0, p1_start
for i in range(p1_start, len(xml)):
    if xml[i:i+6] == '<part ' or xml[i:i+6] == '<part>': depth += 1
    elif xml[i:i+7] == '</part>':
        depth -= 1
        if depth == 0: p1_end = i + 7; break

p1_xml = xml[p1_start:p1_end]

# Extract harmony per measure
for mb in re.finditer(r'<measure\s+number="(\d+)"[^>]*>(.*?)</measure>',
                      p1_xml, re.DOTALL):
    mn = int(mb.group(1))
    for h in re.finditer(r'<harmony[^>]*>(.*?)</harmony>',
                         mb.group(2), re.DOTALL):
        h_full = h.group()
        root = re.search(r'<root-step>([^<]+)</root-step>', h_full)
        kind = re.search(r'<kind[^>]*>(.*?)</kind>', h_full, re.DOTALL)
        # ... extract position and identity
```

## Related

- Korean lyrics on the same page may interfere with chord name classification
  (Audiveris routes text to SentenceInter for lyrics vs ChordNameInter for chords)
- Roller Coaster has 3 staves: Voice (P1), Piano RH (P2 partial), Piano LH (P2 partial)
  — chords appear only above the Voice staff
