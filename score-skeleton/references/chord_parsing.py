"""Chord symbol string parser for music21.

Usage:
    from chord_parsing import make_chordsymbol
    cs = make_chordsymbol('F#m7b5')     # correct kind + pitches + display
    cs = make_chordsymbol('C7#9/Bb')    # slash chord with alteration
    cs = make_chordsymbol('BbM7')       # flat root works correctly

Pitfalls:
    - Do NOT use harmony.ChordSymbol(cn) directly -- built-in parser is
      unreliable for flat roots (BbM7, Eb7) and altered chords (Cm7b5, Cmaj9).
    - Do NOT set cs.chordKindStr -- it masks wrong pitches without fixing them.
      The degree-element approach gives correct display AND correct pitches.
"""

from music21 import harmony, interval
import re

KIND_BY_QUALITY = {
    # simple
    '':        'major',     'M': 'major',       'maj': 'major',   'Maj': 'major',
    'm':       'minor',     'min': 'minor',
    '+':       'augmented', 'aug': 'augmented',
    'dim':     'diminished','o': 'diminished',
    # compound (longer first to win prefix match against shorter keys)
    'Maj7': 'major-seventh',    'Maj9': 'major-ninth',    'Maj11': 'major-11th', 'Maj13': 'major-13th',
    'maj7': 'major-seventh',    'maj9': 'major-ninth',    'maj11': 'major-11th', 'maj13': 'major-13th',
    'M7':   'major-seventh',    'M9':   'major-ninth',    'M11':   'major-11th', 'M13':   'major-13th',
    'min7': 'minor-seventh',    'min9': 'minor-ninth',    'min11': 'minor-11th', 'min13': 'minor-13th',
    'dim7': 'diminished-seventh', 'dim9': 'diminished-ninth', 'dim11': 'diminished-11th',
    # sevenths
    '7':       'dominant-seventh',
    'mM7':     'minor-major-seventh',  'm#7': 'minor-major-seventh',  'minmaj7': 'minor-major-seventh',
    'm7':      'minor-seventh',
    '+M7':     'augmented-major-seventh',  'augmaj7': 'augmented-major-seventh',
    'aug7':    'augmented-seventh',  '7+': 'augmented-seventh',  '+7': 'augmented-seventh',
    'm7b5':    'half-diminished-seventh',  'ø7':      'half-diminished-seventh',
    'o7':      'diminished-seventh',
    # sixths
    '6':       'major-sixth',  'm6': 'minor-sixth',
    # ninths
    '9':       'dominant-ninth',  'm9': 'minor-ninth',  'mM9': 'minor-major-ninth',
    # elevenths
    '11':      'dominant-11th',   'm11': 'minor-11th',  'mM11': 'minor-major-11th',
    # thirteenths
    '13':      'dominant-13th',   'm13': 'minor-13th',  'mM13': 'minor-major-13th',
    # suspended / other
    'sus2':    'suspended-second',
    'sus':     'suspended-fourth',  'sus4': 'suspended-fourth',
    '7sus':    'suspended-fourth-seventh',  '7sus4': 'suspended-fourth-seventh',
    'N6':      'Neapolitan',
    'power':   'power',  'pedal': 'pedal',  '5': 'power',
}


def _parse_alterations(remainder: str) -> list[tuple[int, int, str]]:
    """Parse alteration suffixes from the quality remainder.

    Returns list of (degree, semitones, mod_type) tuples.
    """
    alterations = []
    for m in re.finditer(r'([#b])(\d+)', remainder):
        semitone = -1 if m.group(1) == 'b' else 1
        degree = int(m.group(2))
        # 'alter' for chord tones (3,5,7), 'add' for extensions (9,11,13)
        mod_type = 'alter' if degree in (1, 3, 5, 7) else 'add'
        alterations.append((degree, semitone, mod_type))
    for m in re.finditer(r'add(\d+)', remainder):
        alterations.append((int(m.group(1)), 0, 'add'))
    for m in re.finditer(r'omit(\d+)', remainder):
        alterations.append((int(m.group(1)), 0, 'subtract'))
    return alterations


def parse_chord_string(cn: str) -> dict | None:
    """Parse a chord symbol string into components.

    Returns dict with keys: root, kind, alterations, bass, quality
    Returns None for unparseable input (e.g. 'N.C.', empty).
    """
    if not cn:
        return None
    s = re.sub(r'[\s()]', '', cn)

    # Slash chord bass
    bass = None
    if '/' in s:
        parts = s.split('/', 1)
        s = parts[0]
        bm = re.match(r'^([A-G])(?:[#b]{1,2}|x)?', parts[1])
        bass = bm.group(0) if bm else parts[1]

    # Root note: [A-G] + optional accidentals
    rm = re.match(r'^([A-G])(?:[#b]{1,2}|x)?', s)
    if not rm:
        return None

    quality = s[rm.end():]

    # Base quality match (longest prefix wins for compound entries like 'maj9')
    candidates = sorted(
        [k for k in KIND_BY_QUALITY if k and quality.startswith(k)],
        key=len, reverse=True
    )
    base_q = candidates[0] if candidates else ''
    kind = KIND_BY_QUALITY.get(base_q, 'major')

    remainder = quality[len(base_q):].lstrip()
    alterations = _parse_alterations(remainder)

    return {
        'root': rm.group(0),
        'kind': kind,
        'alterations': alterations,
        'bass': bass,
        'quality': quality,
    }


def make_chordsymbol(cn: str) -> harmony.ChordSymbol:
    """Create a ChordSymbol from a chord string with correct kind + degree alterations.

    No chordKindStr is set -- display is handled by <kind> + <degree> elements
    in MusicXML output.
    """
    parsed = parse_chord_string(cn)
    if parsed is None:
        raise ValueError(f'Cannot parse chord symbol: {cn!r}')

    kwargs: dict = {'root': parsed['root'], 'kind': parsed['kind']}
    if parsed['bass']:
        kwargs['bass'] = parsed['bass']
    cs = harmony.ChordSymbol(**kwargs)

    for deg, semitones, mod_type in parsed['alterations']:
        cs.addChordStepModification(
            harmony.ChordStepModification(
                modType=mod_type,
                degree=deg,
                intervalObj=interval.Interval(semitones),
            )
        )
    return cs
