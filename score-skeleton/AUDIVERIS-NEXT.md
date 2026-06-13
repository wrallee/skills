# Audiveris Integration — Clef & Key Signature Extraction

Status: draft | Last updated: 2026-06-04

**Location:** `~/.hermes/skills/personal/score-skeleton/AUDIVERIS-NEXT.md`
**Scripts:** `audiveris/` (skill subdirectory)
**Output:** `<song>/_audiveris/page-N.mxl` (per-workspace, per-page zipped MusicXML)

## 0. Environment Setup

### Tesseract OCR languages

Required for Korean sheet music with mixed-language text:

```bash
# Check installed languages
tesseract --list-langs

# Expected minimum: eng, kor, ita, fra, deu, osd
# Install missing languages:
TESSDIR=~/.local/share/tessdata   # or /home/wrallee/tessdata_legacy
curl -sL https://github.com/tesseract-ocr/tessdata/raw/main/$LANG.traineddata -o $TESSDIR/$LANG.traineddata
```

### Audiveris OCR language constant

```
-constant Language.defaultSpecification=eng+kor+ita+fra+deu
```

When Audiveris warns `Failed loading language 'chi_tra'`, install Chinese Traditional if needed, or ignore — it's not used for Korean scores.

### Verify

```bash
audiveris -batch -constant Language.defaultSpecification=eng+kor+ita+fra+deu 2>&1 | grep "Installed OCR"
# Expected: Installed OCR languages: deu,eng,fra,ita,kor,osd
```

## 1. Pipeline Integration

### Source Images

Phase 1 (`pdftoppm -png -r 300 -gray`) already produces `_scratch/page-N.png` per page. Feed these directly to Audiveris — no extra conversion needed.

### Audiveris Step Target

Run **up to LINKS** only (skip RHYTHMS which can corrupt measure boundaries):

```bash
# Per page (batch mode, incremental save)
audiveris -batch -step LINKS -save \
  -output _audiveris \
  -constant Language.defaultSpecification=eng+kor+ita+fra+deu \
  _scratch/page-N.png
```

Step chain executed: LOAD → BINARY → SCALE → GRID → HEADERS → STEM_SEEDS → BEAMS → LEDGERS → HEADS → STEMS → REDUCTION → CUE_BEAMS → TEXTS → MEASURES → CHORDS → CURVES → SYMBOLS → LINKS

### Export MusicXML

```bash
audiveris -batch -export -output _audiveris _audiveris/page-N.omr
```

Produces `page-N.mxl` (zipped MusicXML).

## 2. Extracted Data

From Audiveris `<attributes>` blocks per part (at LINKS step):

| Attribute | Source Element | Example | Reliability |
|-----------|---------------|---------|-------------|
| Key signature | `<key><fifths>N</fifths></key>` | `fifths=4` = E major | High |
| Time signature | `<time><beats>N</beats><beat-type>N</beat-type></time>` | 4/4 | High |
| Clef | `<clef><sign>G/F/C</sign><line>N</line></clef>` | G2, F4 | Medium — verify with vision |

### Key signature changes mid-piece

Audiveris exports per-measure `<attributes>` when key changes. This handles mid-piece key signature changes that single-vision-snapshot can't.

### Part structure

Audiveris detects `STAVES_PER_SYSTEM` (e.g., 3 staffs → 3 parts P1/P2/P3). Each part carries its own clef and key at the first measure.

## 3. Measure Reconstruction from Notes

**Problem:** LINKS step produces correct notes/chords but incorrect measure boundaries (because RHYTHMS was skipped and barline detection may be noisy).

**Approach (WIP):**
1. Extract all `<note>` elements from Audiveris `.mxl` in sequence order
2. Use `<divisions>` and `<duration>` for cumulative time tracking
3. Use time signature (`<beats>/<beat-type>`) to determine measure boundaries
4. Re-group notes into correct measures
5. Present reconstructed measures to user for confirmation

### Known Risks
- Staff assignment: notes are tied to `<staff>` within measures; reconstruction must preserve staff grouping
- Grace notes and tuplets: Audiveris may mis-encode these without RHYTHMS
- Multi-page: cross-page measure continuity must be preserved

## 4. Injection into score-skeleton pipeline

```
Phase 4 (target.musicxml generation):
  ├── Parse Audiveris .mxl → extract <attributes> per measure
  ├── Map to our chord_map measures
  ├── Inject clef/key/time into target.musicxml <attributes>
  └── Fallback: if Audiveris unavailable → vision_analyze or user input
```

## 5. Current Status

- [x] OCR languages installed (eng+kor+ita+fra+deu+osd)
- [x] Language constant verified (`-constant Language.defaultSpecification=eng+kor+ita+fra+deu`)
- [x] roller-coaster 6-page Audiveris LINKS run
- [x] untitled page-1 Audiveris LINKS run
- [x] `sheet_to_musicxml.py` — LINKS sheet#1.xml → valid MusicXML with clef/key/time
- [x] Verified: untitled fifths=4, roller-coaster fifths=3
- [ ] to-find-you Audiveris run
- [ ] Multi-page assembly (measure continuity across pages)
- [ ] Injection into score-skeleton Phase 4
- [ ] User confirmation workflow
