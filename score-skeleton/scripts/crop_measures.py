"""Crop chord regions from a page using classified barlines (structure.json).
Barline types by detect_structure.py:
  system_start, system_end — edges, NOT measure boundaries
  thin, double, repeat (*_repeat), final — measure boundaries

Clef/key area removal is done in POST-PROCESS after LLM confirms "empty",
not during cropping. All measures are cropped first; the post-process
step checks: (1) first measure in system, (2) right boundary is start_repeat,
(3) LLM said "empty" → remove lead-in measure.

Usage: python3 crop_measures.py <page_n>
"""
import cv2, json, os, sys

def crop_page(page_num, img_dir='_scratch', struct_dir=None, out_dir=None):
    img_path = f'{img_dir}/page-{page_num}.png'
    if not os.path.exists(img_path):
        print(f"ERROR: {img_path} not found")
        return None

    if struct_dir is None:
        struct_dir = f'{img_dir}/p{page_num}_struct'
    if out_dir is None:
        out_dir = f'{img_dir}/p{page_num}_measures'
    os.makedirs(out_dir, exist_ok=True)

    struct_path = f'{struct_dir}/structure.json'
    with open(struct_path) as f:
        data = json.load(f)

    img = cv2.imread(img_path)
    h, w = img.shape[:2]
    page_offset = 0
    all_measures = []

    for si, sys_info in enumerate(data['systems']):
        s_top = sys_info['y0_page']
        s_bot = sys_info['y1_page']
        vocal_top = sys_info['vocal_staff_top']
        barlines = sys_info['barlines']

        # Chord area (y-offset relative to system top)
        vr = vocal_top - s_top
        cy0 = max(0, vr - 105)
        cy1 = min(s_bot - s_top, vr + 5)

        # Extract real measure boundaries from classified barlines
        meas_x = []
        barline_types = []
        for b in barlines:
            if b['type'] in ('system_start', 'system_end'):
                continue
            meas_x.append(b['x'])
            barline_types.append(b['type'])

        start_x = None
        end_x = None
        for b in barlines:
            if b['type'] == 'system_start':
                start_x = b['x']
            elif b['type'] == 'system_end':
                end_x = b['x']

        if start_x is None:
            start_x = barlines[0]['x']
        if end_x is None:
            end_x = barlines[-1]['x']

        all_x = [start_x] + meas_x + [end_x]

        system_meas = 0
        for mi in range(len(all_x) - 1):
            x1 = all_x[mi]
            x2 = all_x[mi+1]
            x1_pad = max(0, x1 + 3)
            x2_pad = min(w, x2 - 3)
            if x2_pad <= x1_pad:
                continue

            crop = img[s_top + cy0 : s_top + cy1, x1_pad : x2_pad]
            if crop.size == 0:
                continue

            global_mn = page_offset + system_meas + 1
            out_path = f'{out_dir}/M{global_mn:02d}.png'
            cv2.imwrite(out_path, crop)
            all_measures.append({
                'global': global_mn, 'system': si, 'local': mi,
                'x0': x1, 'x1': x2,
                'left_type': 'system_start' if mi == 0 else barline_types[mi-1],
                'right_type': 'system_end' if mi == len(all_x)-2 else barline_types[mi],
                'path': out_path
            })
            system_meas += 1

        page_offset += system_meas

    # Save manifest for post-processing
    manifest = f'{out_dir}/_manifest.json'
    with open(manifest, 'w') as f:
        json.dump(all_measures, f, indent=2)

    return all_measures

if __name__ == '__main__':
    pn = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    r = crop_page(pn)
    if r:
        print(f"Page {pn}: {len(r)} measures")
