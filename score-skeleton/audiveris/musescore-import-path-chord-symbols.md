# MuseScore MusicXML Import Path for Chord Symbols

Source: `MuseScore` master branch commit analyzed 2026-06-03.
Path: `src/importexport/musicxml/internal/import/importmusicxmlpass2.cpp`
      `src/engraving/dom/chordlist.cpp`
      `src/engraving/dom/harmony.cpp`
      `src/importexport/musicxml/internal/shared/musicxmlsupport.cpp`

## Import Flow (simplified)

1. **`importmusicxmlpass2.cpp:7849-7856`**: reads `<kind text="...">kind-value</kind>`.
   - `kindText = m_e.attribute("text")` → holds whatever we set in `chordKindStr`.
   - `kind = m_e.readText()` → the MusicXML kind-value (e.g. `major-seventh`, `suspended-fourth`, `dominant`).

2. **`importmusicxmlpass2.cpp:7887-7915`**: reads `<degree>` elements into `degreeList`.

3. **`musicxmlsupport.cpp:715-719`**: `harmonyFromXml()` calls `ParsedChord::fromXml(kind, kindText, symbols, parens, degreeList, chordList)` → sets `info->setTextName(pc->fromXml(...))` → then `info->getDescription(info->textName(), pc)`.

4. **`chordlist.cpp:1332`**: `ParsedChord::fromXml()` — the critical function.
   - Lines 1345-1396: maps `kind` value to internal quality + modifiers.
     - `suspended-fourth` → `quality=major`, `implied=true`, modifier `sus4`.
     - `dominant-seventh` → `quality=dominant`, `implied=true`, `extension=7`.
   - Lines 1412-1467: degree list → modifier list conversion.
     - `ADD alter=-1` → modifier `b{value}` (e.g. `b7` → visible flat on 7th).
     - `ADD alter=0` → modifier `add{value}`.
     - **Lines 1435-1439 (key pitfall for 7sus4/9sus4)**: when kind contains `suspended` AND degree is `add7`:
       ```cpp
       if (mod == "add7" && kind.contains("suspended")) {
           m_quality = "dominant";
           implied = true;
           extension = 7;
           extend = true;
           mod = "";
       }
       ```
       This converts `suspended-fourth + add7(alter=0)` → dominant 7 internally. **`addb7` (alter=-1) does NOT hit this path** — it stays as visible `b7` modifier → `Bsus4b7add9`.

   - Lines 1498-1506: **`kindText` validation**. RE-PARSES `kindText` as a chord to verify it produces the same kind with no extra degrees. If it fails, `kindText` is cleared.
     - This means `kindText="M7"` → parsed → `kind="major-seventh"` → passes.
     - But `kindText="7sus4"` → parsed → `kind="suspended-fourth"` + degrees → **FAILS** because the re-parse produces degrees. So `kindText` gets CLEARED. This means `7sus4`/`9sus4` as `kind@text` gets dropped.

   - Lines 1508-1517: **name construction**.
     - If `kindText` non-empty → use `kindText` as display name (with extension prefix for sus chords).
     - Otherwise → construct from quality + extension (e.g. `maj7` for major quality + extension 7).

   - Lines 1552-1553: re-parses constructed name → generates handle → `parse(m_name, cl, true)`.

5. **`importmusicxmlpass2.cpp:7937-7947`**: back in the importer.
   ```cpp
   d = harmonyFromXml(info, m_score, kind, kindText, symbols, parens, degreeList);
   if (d) {
       info->setId(d->id);
       info->setTextName(d->names.front());  // OVERWRITES with chord-list name
   }
   ```
   - If a `ChordDescription` is found (by exact name or parsed handle match), `textName` is overwritten with `d->names.front()`.
   - This is why **M7 → maj7**: the handle for `major-seventh` quality matches the built-in `maj7` entry, whose first name is `maj7`.

6. **`harmony.cpp:81-104`**: `descr(name, pc)` — lookup.
   - Exact name match first.
   - Fallback: parsed handle match (`ParsedChord::operator==` compares `m_handle`).
   - Handle for M7 text: `<major><7>` vs handle for maj7: also `<major><7>` → same handle → match → canonicalizes to `maj7`.

## Key Implications for score-skeleton

### 7sus4 / 9sus4 — correct construction

**RIGHT**: `dominant-seventh` + subtract 3 + add 4 (or `dominant` + subtract 3 + add 4)
- kind = `dominant` or `dominant-seventh` or `dominant-ninth`
- `subtract 3` hides the 3rd away
- `add 4` adds the sus4
- Export: `<kind text="7sus4">dominant</kind>` + hidden degrees
- MuseScore import: `dominant` → quality=dominant, degrees convert cleanly. No visible `b7`.

**WRONG**: `suspended-fourth` + add 7 (alter -1)
- kind = `suspended-fourth`
- add degree 7 with alter=-1 (b7)
- Export: `<kind text="7sus4">suspended-fourth</kind>` + `<degree-alter>-1</degree-alter>`
- MuseScore import: `suspended-fourth` → quality=major, modifier=sus4. Degree add7 alter=-1 → modifier `b7`. kindText `7sus4` re-parses with degrees → validation fails → kindText cleared. Result: `Bsus4b7add9` instead of `B7sus4`.

### M7 → maj7

`<kind text="M7">major-seventh</kind>` is semantically correct. But MuseScore imports it, handle `<major><7>` matches the built-in `maj7` entry (also handle `<major><7>`), so it canonicalizes to `maj7`. This is an accepted trade-off — the chord meaning is unchanged.

To force MuseScore to display `M7`, you would need a custom chord-list entry or a non-MusicXML path (e.g. a `<direction>` text element instead of `<harmony>`).

### `kind@text` is not a reliable MuseScore display contract

Setting `<kind text="X">` does NOT guarantee MuseScore shows `X`. MuseScore:
1. Reads `kind@text` into `kindText`.
2. Validates `kindText` by re-parsing it — if it produces extra degrees, `kindText` is discarded (7sus4/9sus4 case).
3. Even if `kindText` passes, the parsed handle may match a chord-list entry whose `names.front()` replaces `textName` (M7→maj7 case).

Always verify MuseScore display with an actual import/export probe, not just by reading the XML.

## MuseScore Test Data Confirmation

`testHarmony2.xml` lines 188-208 show MuseScore's own expected pattern for a sus4-dominant hybrid:
```xml
<kind>suspended-fourth</kind>
<degree><degree-value>7</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type></degree>
<degree><degree-value>9</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type></degree>
```
This uses `suspended-fourth + add7(alter=0) + add9`. The alter=0 is critical — it triggers the `add7 + suspended` → dominant path in chordlist.cpp:1435-1439. Our preferred `dominant-ninth + subtract3 + add4` is semantically equivalent and avoids the `suspended-fourth-seventh` kind-value issue.
