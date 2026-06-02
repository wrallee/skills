# MusicXML representation for 7sus4 chords

Session finding: `E7sus4` / `E7sus` should not be exported as `<kind>suspended-fourth-seventh</kind>` because `suspended-fourth-seventh` is not a MusicXML `kind-value`.

Authoritative MusicXML 4.0 references checked:

- `kind-value`: https://www.w3.org/2021/06/musicxml40/musicxml-reference/data-types/kind-value/
  - A `kind-value` is a chord starting point; `<degree>` elements can add, subtract, or alter from that starting point.
  - Suspended kind-values include `suspended-second` and `suspended-fourth`; there is no `suspended-fourth-seventh`.
- `kind`: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/kind/
  - The `text` attribute may use strings such as `13sus` that refer to both the kind and one or more `<degree>` elements.
  - In that case, the corresponding `<degree>` elements should use `print-object="no"` to avoid redundant rendering.
- `degree`: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/degree/
  - `<degree>` adds, alters, or subtracts individual chord notes.
  - `print-object` can hide a degree already accounted for in the `<kind text="...">` display string.
- `degree-alter`: https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/degree-alter/
  - For `degree-type=add`, `degree-alter` is relative to a dominant chord: major/perfect intervals except minor seventh.
  - Therefore an added minor seventh is `<degree-value>7</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type>`.

Recommended encoding for `E7sus4`:

```xml
<harmony>
  <root>
    <root-step>E</root-step>
  </root>
  <kind text="7sus4">suspended-fourth</kind>
  <degree print-object="no">
    <degree-value>7</degree-value>
    <degree-alter>0</degree-alter>
    <degree-type>add</degree-type>
  </degree>
</harmony>
```

Semantic reading: `suspended-fourth` gives `E A B`; hidden added seventh gives `D`; `text="7sus4"` preserves the lead-sheet display.

Alternative valid but more verbose analysis:

```xml
<kind text="7sus4">dominant</kind>
<degree print-object="no"><degree-value>3</degree-value><degree-alter>0</degree-alter><degree-type>subtract</degree-type></degree>
<degree print-object="no"><degree-value>4</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type></degree>
```

Prefer the `suspended-fourth` + hidden add-7 representation because it is closer to the written chord and avoids modeling the suspended fourth as two operations against a dominant starting point.
