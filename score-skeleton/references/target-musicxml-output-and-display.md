# Plain `target.musicxml` output and display postprocess

Session-derived rule for score-skeleton transcription outputs.

## Durable workflow decision

Generate **plain uncompressed MusicXML** as the only deliverable:

- Output filename: `target.musicxml`
- Do not create `.mxl` compressed packages.
- Do not keep an optional `target.mxl` path in the default workflow.
- Do not use nonstandard `.musicmxl` extension.
- MuseScore can open/import standard `.musicxml` / `.xml` files directly, and the file can be inspected in Notepad/VS Code.

## Why

Compressed `.mxl` hid the actual XML inside a package and made it unclear whether files were overwritten or post-processed correctly. Plain `target.musicxml` makes verification direct and avoids attachment/inspection confusion.

## Implementation pattern

Write MusicXML directly:

```python
base_path = os.path.join(song_dir, '_base.musicxml')
score.write('musicxml', base_path)
score2 = converter.parse(base_path)

final_path = os.path.join(song_dir, 'target.musicxml')
score2.write('musicxml', final_path)
display_patched = postprocess_harmony_display(final_path, chord_map)
```

Post-process `target.musicxml` directly with `xml.etree.ElementTree`; do not open a zip and rewrite an internal `final.musicxml` member.

```python
def postprocess_harmony_display(xml_path, chord_map):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    # Patch <kind text="M7">, <kind text="7sus4">, <kind text="9sus4">
    # and hide implementation-only <degree print-object="no"> where needed.
    tree.write(xml_path, encoding='utf-8', xml_declaration=True)
```

## Verification

After generation:

```bash
find . -name '*.mxl' -print   # must print nothing
file */target.musicxml        # should be XML/plain text
```

Then parse with music21 and also inspect the XML text directly for visible display rules (`text="M7"`, `text="7sus4"`, `text="9sus4"`, `print-object="no"`). Chord counts alone verify semantics, not rendered chord text.
