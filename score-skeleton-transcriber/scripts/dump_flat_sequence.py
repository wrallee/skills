#!/home/wrallee/.hermes/hermes-agent/venv/bin/python3
"""
Flatten .mxl notes into a sequential stream for LLM analysis of measure structure.
Output: one line per note with (index, pitch, dur, cumulative, meas#, beat, type, beams, tie, tuplet)
"""
import sys, zipfile, re

mxl = sys.argv[1]
voice_filter = None
filter_vid = None
if len(sys.argv) >= 4 and sys.argv[2] == '--voice':
    filter_vid = sys.argv[3]

with zipfile.ZipFile(mxl) as z:
    for name in z.namelist():
        if 'META' not in name and name.endswith('.xml'):
            text = z.read(name).decode('utf-8')
            break

divisions = int(re.search(r'<divisions>(\d+)</divisions>', text).group(1))
bar_dur = 4 * divisions

parts = re.findall(r'<part[^>]*>(.*?)</part>', text, re.DOTALL)

for pi, p in enumerate(parts):
    pid = re.search(r'id="([^"]*)"', p)
    pid = pid.group(1) if pid else f'P{pi}'
    pname = re.search(r'part-name>([^<]+)', p)
    pname = pname.group(1) if pname else '(unnamed)'

    voice_notes = {}
    global_offset = {}

    meas_xmls = re.findall(r'<measure[^>]*>.*?</measure>', p, re.DOTALL)

    for mx in meas_xmls:
        for m2 in re.finditer(r'(<note[^>]*>.*?</note>|<backup>.*?</backup>|<forward>.*?</forward>)', mx, re.DOTALL):
            el = m2.group()
            if el.startswith('<backup'):
                d = re.search(r'<duration>(\d+)</duration>', el)
                if d:
                    back = int(d.group(1))
                    for v in global_offset:
                        global_offset[v] = max(0, global_offset[v] - back)
            elif el.startswith('<forward'):
                d = re.search(r'<duration>(\d+)</duration>', el)
                if d:
                    for v in global_offset:
                        global_offset[v] += int(d.group(1))
            elif el.startswith('<note'):
                chord = '<chord>' in el or '<chord />' in el
                if chord:
                    continue
                v = re.search(r'<voice>(\d+)</voice>', el)
                d = re.search(r'<duration>(\d+)</duration>', el)
                t_m = re.search(r'<type>([^<]+)</type>', el)
                t = t_m.group(1) if t_m else '?'
                rest = '<rest' in el

                vid = v.group(1) if v else '1'
                dur = int(d.group(1)) if d else 0

                if rest:
                    pitch = 'R'
                else:
                    step = re.search(r'<step>([^<]+)', el)
                    oct = re.search(r'<octave>(\d+)', el)
                    alt = re.search(r'<alter>([-\d]+)', el)
                    s = step.group(1) if step else '?'
                    o = oct.group(1) if oct else '?'
                    a = '#' if alt and alt.group(1) == '1' else 'b' if alt and alt.group(1) == '-1' else ''
                    pitch = f'{s}{a}{o}'

                beams = '/'.join(re.findall(r'<beam[^>]*>([^<]+)</beam>', el))
                tie_m = re.search(r'<tie type="([^"]+)"', el)
                tie = tie_m.group(1) if tie_m else ''
                tm = re.search(r'<time-modification>.*?<actual-notes>(\d+)</actual-notes>.*?<normal-notes>(\d+)</normal-notes>', el, re.DOTALL)
                tup = f'tup({tm.group(1)}/{tm.group(2)})' if tm else ''

                off = global_offset.get(vid, 0)
                if vid not in voice_notes:
                    voice_notes[vid] = []
                voice_notes[vid].append({'pitch': pitch, 'dur': dur, 'type': t, 'offset': off, 'beams': beams, 'tie': tie, 'tuplet': tup})
                global_offset[vid] = off + dur

    max_off = max((global_offset[v] for v in global_offset), default=0)

    for vid in sorted(voice_notes.keys()):
        if filter_vid and vid != filter_vid:
            continue
        notes = voice_notes[vid]
        print(f"PART {pid} ({pname}) — V{vid} ({len(notes)} notes, {max_off/divisions:.1f}ql = ~{max_off/bar_dur:.0f} measures)")
        cum = 0
        for i, n in enumerate(notes):
            cum += n['dur']
            meas_n = cum // bar_dur
            frac = (cum % bar_dur) / bar_dur
            print(f"  {i:>4} {n['pitch']:>6} {n['dur']:>5} {cum:>6} M{meas_n}.{frac*4:.1f} {n['type']:>8} {n['beams']:>12} {n['tie']:>6} {n['tuplet']:>10}")
