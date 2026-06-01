#!/usr/bin/env python3
"""Strip an Audiveris LINKS .mxl down to its structural skeleton.

Removes all notes, lyrics, harmonies, and non-Voice parts.
Keeps measures, system/page breaks, key, time, clef.
Result: blank canvas ready for chord injection.

Usage:
    python scripts/strip_to_skeleton.py input.mxl output.mxl
"""
import zipfile, re, os, sys

def strip(src, dst):
    with zipfile.ZipFile(src, 'r') as z:
        xml_name = [n for n in z.namelist()
                    if 'META' not in n and ('.xml' in n or '.musicxml' in n)][0]
        xml = z.read(xml_name).decode('utf-8')

    # Keep only first <part>
    xml = xml.split('</part>')[0] + '</part>\n</score>'

    # Remove content — keep structural elements (print, attributes, direction)
    xml = re.sub(r'<note>.*?</note>', '', xml, flags=re.DOTALL)
    xml = re.sub(r'<lyric[^>]*>.*?</lyric>', '', xml, flags=re.DOTALL)
    xml = re.sub(r'<harmony[^>]*>.*?</harmony>', '', xml, flags=re.DOTALL)
    xml = re.sub(r'<backup>.*?</backup>', '', xml, flags=re.DOTALL)
    xml = re.sub(r'<forward>.*?</forward>', '', xml, flags=re.DOTALL)

    # Add whole rest to empty measures
    def add_rest(m):
        if '<note>' not in m.group(2):
            return (m.group(1)
                    + '<note><rest/><duration>4</duration><type>whole</type></note>'
                    + m.group(3))
        return m.group(0)

    xml = re.sub(r'(<measure[^>]*>)(.*?)(</measure>)', add_rest, xml, flags=re.DOTALL)

    # Write temp + rebuild
    tmp = os.path.join('/tmp', 'stripped_' + xml_name)
    with open(tmp, 'w') as f:
        f.write(xml)

    with zipfile.ZipFile(src, 'r') as zin:
        with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == xml_name:
                    zout.write(tmp, xml_name)
                else:
                    zout.writestr(item, zin.read(item.filename))
    os.remove(tmp)

    # Report
    with zipfile.ZipFile(dst, 'r') as z:
        xml2 = z.read(xml_name).decode('utf-8')
    ms = len(re.findall(r'<measure[^>]*number="', xml2))
    sys_b = xml2.count('new-system="yes"')
    pg_b = xml2.count('new-page="yes"')
    print(f"Skeleton: {ms} measures, {sys_b} system breaks, {pg_b} page breaks")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.mxl output.mxl")
        sys.exit(1)
    strip(sys.argv[1], sys.argv[2])
