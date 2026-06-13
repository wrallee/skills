# MuseScore Harmony Import Path (source analysis)

How MuseScore 4.x processes MusicXML `<harmony>` on import, and what it means for display text control.

**Source files:**
- `src/importexport/musicxml/internal/shared/musicxmlsupport.cpp` — `harmonyFromXml()`
- `src/importexport/musicxml/internal/import/importmusicxmlpass2.cpp` — harmony element parser (~line 7800)
- `src/engraving/dom/chordlist.cpp` — `ParsedChord::fromXml()` (~line 1332), `ParsedChord::parse()` (~line 579)
- `src/engraving/dom/harmony.cpp` — `HarmonyInfo::descr()`, `getDescription()` (~line 66)

## Import flow

1. `importmusicxmlpass2.cpp:7849-7856` — reads `<kind text="X">` into `kindText`, `<kind>Y</kind>` into `kind`
2. `importmusicxmlpass2.cpp:7887-7915` — reads `<degree>` elements into `degreeList`
3. `importmusicxmlpass2.cpp:7937-7939` — calls `harmonyFromXml(info, score, kind, kindText, symbols, parens, degreeList)`
4. `musicxmlsupport.cpp:715-719` — creates `ParsedChord`, calls `fromXml()`, then `getDescription(textName, pc)`
5. `importmusicxmlpass2.cpp:7941-7947` — **if** `ChordDescription* d` is found, overwrites `textName` with `d->names.front()`; **else** falls back to `functionText + kindText + inversionText`

## Key finding: kind@text is read but not authoritative

```
if (d) {
    info->setId(d->id);
    info->setTextName(d->names.front());  // ← OVERWRITTEN by chord list name
} else {
    info->setId(-1);
    String textName = functionText + kindText + inversionText;
    info->setTextName(textName);
}
```

If `harmonyFromXml()` finds a matching `ChordDescription` in the score's chord list, the `kind@text` value is **discarded** and replaced by the chord list's canonical name. The chord list is populated from:
- Built-in defaults (from `chords.xml` in MuseScore resources)
- Chords already encountered in the current score

## `ParsedChord::fromXml()` name construction

In `chordlist.cpp:1332-1568`, when `kindText` is non-empty AND `kind != "none"` AND `kind != "other"`:

```cpp
// validate kindText (1498-1505)
ParsedChord validate;
validate.parse(kindText, cl, false);
if (validate.m_xmlKind != kind || !validate.m_xmlDegrees.empty()) {
    kindText = u"";   // ← INVALIDATED if doesn't parse back to same kind
}

// construct name (1508-1552)
if (!kindText.empty()) {
    // Extension prefix for suspended chords (1510-1512)
    if (!m_extension.empty() && kind.contains(u"suspended")) {
        m_name += m_extension;   // e.g. "7" + "sus4" = "7sus4"
    }
    m_name += kindText;
} else if (implied) {
    m_name = m_extension;
} else {
    // Build from quality abbreviations:
    // major→maj, minor→m, augmented→aug, diminished→dim, half-diminished→m7b5
    m_name = quality_abbrev + m_extension;
}
```

### M7 path
- `<kind text="M7">major-seventh</kind>`
- `fromXml()`: `kind="major-seventh"`, `kindText="M7"`
- Validate: `parse("M7")` → `m_xmlKind="major"`? Wait, `M7` — the parser sees `M` as quality (major), `7` as extension → `m_xmlKind="major"`, `m_extension="7"`. Since `kind="major-seventh"` — no `"seventh"` in `m_xmlKind` → validation fails → `kindText=""`
- Then: `m_quality="major"`, implied=false → `m_name="maj7"` (sym=false)
- **`M7` kindText is rejected by validation because it parses as `major`+7, not `major-seventh`**

### 7sus4 path (dominant + subtract3 + add4)
- `<kind text="7sus4">dominant</kind>` with `<degree>subtract 3</degree><degree>add 4</degree>`
- `fromXml()`: `kind="dominant"`, `kindText="7sus4"`
- `kind.contains("dominant")` → `m_quality="dominant"`, `implied=true`, `extension=7` (from dominant kind logic)
- Validate: `parse("7sus4")` → the parser sees `7` as extension, `sus4` as modifier. `sus4` → `m_xmlKind="suspended-fourth"`. This does NOT equal `kind="dominant"` → validation fails → `kindText=""`
- Then: `m_quality="dominant"`, `implied=true` → `m_name="7"`. But modifiers: `subtract 3` = `no3`, `add 4` = `add4`. `no3+add4` → `sus4` (line 1468-1480). Final `m_name = "7" + "sus4"` = `"7sus4"`
- **The name `"7sus4"` comes from modifier reconstruction, NOT from kindText**

### 9sus4 path
- `<kind text="9sus4">dominant-ninth</kind>` with degrees
- Similar: `kindText="9sus4"` rejected by validation, but `9` extension + `sus4` modifier reconstruction yields `"9sus4"`

## Implications for score-skeleton

| What we want | XML we write | MuseScore shows | Why |
|---|---|---|---|
| `Bsus4b7add9` | `<kind text="9sus4">suspended-fourth</kind>` + `<degree>add b7</degree>` | `Bsus4b7add9` | kindText="9sus4" rejected (parses as suspended-fourth, not matching). degree `b7` becomes visible modifier. |
| `B9sus4` (OK) | `<kind text="9sus4">dominant-ninth</kind>` + `<degree>subtract 3</degree><degree>add 4</degree>` | `B9sus4` | kindText rejected, but `9` extension + `sus4` modifier reconstruction → name="9sus4" |
| `Esus4b7add9` | `<kind text="7sus4">suspended-fourth</kind>` + `<degree>add b7</degree>` | `Esus4b7add9` | Same as Bsus4b7add9 case |
| `E7sus4` (OK) | `<kind text="7sus4">dominant</kind>` + `<degree>subtract 3</degree><degree>add 4</degree>` | `E7sus4` | kindText rejected, but `7` extension + `sus4` modifier reconstruction → name="7sus4" |
| `AM7` | `<kind text="M7">major-seventh</kind>` | `Amaj7` | kindText="M7" rejected (parses as major+7, not major-seventh). Falls to default abbreviation: `maj7` |

## Bottom line

- **`kind@text` alone cannot control MuseScore display** for chords that MuseScore's parser can decompose
- The parser validates: kindText must round-trip (parse back to the same MusicXML kind). If it doesn't, kindText is discarded
- **`7sus4`/`9sus4` workaround**: use `dominant`/`dominant-ninth` kind + `subtract 3` + `add 4` degrees. The parser's modifier reconstruction (`no3+add4→sus4`) produces the correct name
- **`M7` → `maj7`**: no plain-MusicXML workaround. MuseScore's default chord list canonicalizes to `maj7`. This is an accepted trade-off
