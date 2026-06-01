"""Structure detector: staffs → systems → barlines (classified).
Detects vertical lines, groups nearby (<20px), detects repeat dots,
classifies each barline, outputs JSON.

Barline types:
  system_start  — left edge of system (thick bracket)
  system_end    — right edge of system (thick)
  thin          — regular single barline
  double        — two thin lines close together (section boundary, no dots)
  start_repeat  — ||:  (lines + dots to the right)
  end_repeat    — :||  (lines + dots to the left)
  end_start_repeat — :||: (lines + dots both sides)
  final         — thin+thick (end of piece)
  unknown       — detected but unclassified

Usage: python3 scripts/detect_structure.py <page_n>
"""
import cv2, numpy as np, os, json, sys

MERGE_THRESHOLD = 20  # px: compound barline grouping (inc. repeat signs)
DOT_DISTANCE = 35     # px: max distance from compound center to look for dots
DOT_MIN_AREA = 20     # below: noise speck; above: staff junction/lyric dot
DOT_MAX_AREA = 120

def detect_dots(gray_segment, x_center, staff_ys):
    """Detect small round repeat-dot blobs near x_center within staff y-ranges."""
    h = gray_segment.shape[0]
    # Search strip: ±DOT_DISTANCE around x_center, full height
    x1 = max(0, x_center - DOT_DISTANCE)
    x2 = min(gray_segment.shape[1], x_center + DOT_DISTANCE)
    strip = gray_segment[:, x1:x2]
    _, bin = cv2.threshold(strip, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(bin, connectivity=8)

    dots = []
    for i in range(1, n):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]
        a = stats[i, cv2.CC_STAT_AREA]
        cx, cy = centroids[i]

        # Area+size filter: exclude noise (<20px²), staff junctions (>120px²)
        if not (DOT_MIN_AREA < a < DOT_MAX_AREA and 4 < cw < 20 and 4 < ch < 20):
            continue

        # Circularity filter
        perimeter = 2 * (cw + ch)
        circ = 4 * np.pi * a / (perimeter * perimeter) if perimeter > 0 else 0
        if circ < 0.5:
            continue

        # Must be within a staff region (between staff tops and bottoms)
        in_staff = False
        for sy0, sy1 in staff_ys:
            if sy0 - 10 < cy < sy1 + 10:
                in_staff = True
                break
        if not in_staff:
            continue

        dots.append({
            'x': x1 + int(cx), 'y': int(cy),
            'w': cw, 'h': ch, 'area': a, 'circ': circ
        })

    return dots

def classify_barline_group(lines, dots_rel, staff_ys, page_w, is_first_group, is_last_group):
    """Classify a group of close vertical lines."""
    n = len(lines)
    if is_first_group:
        return 'system_start'

    gx = (lines[0]['x'] + lines[-1]['x']) // 2
    left_dots = [d for d in dots_rel if d['x'] < gx]
    right_dots = [d for d in dots_rel if d['x'] >= gx]
    has_left = len(left_dots) >= 2
    has_right = len(right_dots) >= 2

    # Repeat signs may appear at a system end; classify dots before falling back
    # to generic system_end.
    if n > 1:
        if has_left and has_right:
            return 'end_start_repeat'
        elif has_right:
            return 'start_repeat'
        elif has_left:
            return 'end_repeat'

        # Standard final barline = thin + thick, usually at final system end.
        last_thick = lines[-1].get('thickness', 1) > 6
        if is_last_group and last_thick:
            return 'final'
        if not is_last_group:
            return 'double'

    if is_last_group:
        return 'system_end'
    if n == 1:
        return 'thin'
    return 'double'

def group_staves_by_vertical_gaps(staves):
    """Group detected staves into systems without assuming a fixed stave count.

    The split threshold is learned from adjacent staff gaps. Within-system gaps
    are usually smaller than between-system gaps; if no clear two-cluster split
    exists, fall back to a staff-height-scaled threshold so 1-stave lead sheets
    still split between systems.
    """
    if not staves:
        return []
    staves = sorted(staves, key=lambda s: s['top'])
    if len(staves) == 1:
        return [staves]

    gaps = [staves[i + 1]['top'] - staves[i]['bot'] for i in range(len(staves) - 1)]
    heights = [s['bot'] - s['top'] for s in staves]
    med_height = float(np.median(heights)) if heights else 70.0
    base_threshold = max(90.0, med_height * 1.6)

    pos_gaps = sorted(g for g in gaps if g > 0)
    threshold = base_threshold
    if len(pos_gaps) >= 2:
        best_ratio = 0.0
        best_mid = None
        for a, b in zip(pos_gaps, pos_gaps[1:]):
            ratio = b / max(a, 1)
            if ratio > best_ratio:
                best_ratio = ratio
                best_mid = (a + b) / 2.0
        if best_mid is not None and best_ratio >= 1.45:
            threshold = best_mid

    systems = []
    current = [staves[0]]
    for gap, staff in zip(gaps, staves[1:]):
        if gap > threshold:
            systems.append(current)
            current = [staff]
        else:
            current.append(staff)
    systems.append(current)
    return systems

def detect_page(page_num, img_dir='_scratch', out_dir=None):
    path = f'{img_dir}/page-{page_num}.png'
    if not os.path.exists(path):
        print(f"ERROR: {path} not found"); return None
    if out_dir is None:
        out_dir = f'{img_dir}/p{page_num}_struct'
    os.makedirs(out_dir, exist_ok=True)

    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]
    _, global_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)

    # --- Staff detection ---
    proj = np.sum(global_bin, axis=1) // 255
    in_l = False
    peaks = []
    for y, val in enumerate(proj):
        if val > w*0.25 and not in_l:
            ls = y; in_l = True
        elif val <= w*0.25 and in_l:
            if y - ls >= 2: peaks.append((ls + y)//2)
            in_l = False
    if in_l and h - ls >= 2: peaks.append((ls + h)//2)

    used = set()
    staves = []
    i = 0
    while i < len(peaks) - 4:
        if i in used: i += 1; continue
        t = peaks[i]
        # Try multiple inter-line spacings (13-21px) for varied DPI/layouts
        best_found = None
        for spacing in range(13, 22):
            expected = [t + spacing * (j+1) for j in range(4)]
            f = [t]; pos = i + 1; ok = True; tol = 4
            for exp in expected:
                while pos < len(peaks) and peaks[pos] < exp - tol: pos += 1
                if pos < len(peaks) and abs(peaks[pos] - exp) <= tol:
                    f.append(peaks[pos]); used.add(pos); pos += 1
                else: ok = False; break
            if ok:
                best_found = f
                break
        if best_found:
            staves.append({'top': best_found[0], 'bot': best_found[-1], 'line_count': len(best_found)})
            used.add(i)
        i += 1

    # Group staves into systems by vertical gaps; do not assume fixed stave count.
    raw_systems = [s for s in group_staves_by_vertical_gaps(staves) if len(s) >= 1]

    stave_counts = [len(s) for s in raw_systems]
    print(f"Page {page_num}: {len(raw_systems)} systems, {len(staves)} staves | stave_counts={stave_counts}")

    result = {'page': page_num, 'systems': []}

    for si, sys_staves in enumerate(raw_systems):
        first_staff = sys_staves[0]
        last_staff = sys_staves[-1]
        s_top = max(0, first_staff['top'] - 90)
        s_bot = min(h, last_staff['bot'] + 30)
        sys_gray = gray[s_top:s_bot, :]
        _, sys_bin = cv2.threshold(sys_gray, 0, 255, cv2.THRESH_OTSU | cv2.THRESH_BINARY_INV)
        sys_h = s_bot - s_top
        sys_w = sys_gray.shape[1]

        # --- Vertical line detection ---
        vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(sys_h*0.4)))
        vl = cv2.morphologyEx(sys_bin, cv2.MORPH_OPEN, vk)
        cp = np.sum(vl, axis=0)//255

        raw_lines = []
        in_l = False
        for x, val in enumerate(cp):
            if val > 5 and not in_l:
                ls = x; in_l = True
            elif val <= 5 and in_l:
                le = x
                if le - ls >= 2:
                    raw_lines.append({
                        'x': (ls+le)//2,
                        'x0': ls, 'x1': le,
                        'thickness': le - ls
                    })
                in_l = False
        if in_l and sys_w-ls >= 2:
            raw_lines.append({
                'x': (ls+sys_w)//2,
                'x0': ls, 'x1': sys_w-1,
                'thickness': sys_w-ls
            })

        if len(raw_lines) < 2:
            print(f"  System {si}: too few lines ({len(raw_lines)}), skipping")
            continue

        first_line = raw_lines[0]
        last_line = raw_lines[-1]

        # --- Group close lines ---
        groups = []
        current = [raw_lines[0]]
        for line in raw_lines[1:]:
            if line['x'] - current[-1]['x'] < MERGE_THRESHOLD:
                current.append(line)
            else:
                groups.append(current)
                current = [line]
        groups.append(current)

        # Staff Y ranges (for dot filtering)
        staff_ys = [(s['top'] - s_top, s['bot'] - s_top) for s in sys_staves]

        # --- Classify each group ---
        classified = []
        for gi, g in enumerate(groups):
            gx = (g[0]['x'] + g[-1]['x']) // 2
            gx0 = g[0]['x0']
            gx1 = g[-1]['x1']

            # Detect dots near this group
            dots = detect_dots(sys_gray, gx, staff_ys)

            btype = classify_barline_group(
                g, dots, staff_ys, sys_w,
                gi == 0, gi == len(groups) - 1
            )

            classified.append({
                'type': btype,
                'x': gx,
                'x0': gx0,
                'x1': gx1,
                'num_lines': len(g),
                'individual_x': [l['x'] for l in g],
                'thicknesses': [l['thickness'] for l in g],
                'dots_left': len([d for d in dots if d['x'] < gx]),
                'dots_right': len([d for d in dots if d['x'] >= gx])
            })

        # --- Derive measure boundaries ---
        # A measure gap is the horizontal span between consecutive classified
        # barline groups. Downstream code may mark the first system_start →
        # start_repeat gap as a setup pseudo-gap, but the detector keeps all
        # gaps raw so chordless real measures are not discarded here.
        n_meas = len(classified) - 1

        measure_gaps = []
        for gi in range(len(classified) - 1):
            left = classified[gi]
            right = classified[gi + 1]
            measure_gaps.append({
                'gap_idx': gi,
                'x0': left['x'],
                'x1': right['x'],
                'left_type': left['type'],
                'right_type': right['type'],
                'width': right['x'] - left['x']
            })

        # Build compact boundary array for debugging/inspection.
        meas_boundaries = []
        for b in classified:
            if b['type'] == 'system_start':
                meas_boundaries.append(('start', b['x']))
            elif b['type'] == 'system_end':
                meas_boundaries.append(('end', b['x']))
            else:
                meas_boundaries.append(('bar', b['x']))

        # Save debug image
        debug = img[s_top:s_bot, :].copy()
        colors = {
            'system_start': (0, 0, 200),
            'system_end': (0, 0, 200),
            'thin': (0, 255, 0),
            'double': (255, 165, 0),
            'start_repeat': (0, 255, 255),
            'end_repeat': (255, 0, 255),
            'end_start_repeat': (255, 255, 0),
            'final': (0, 0, 255),
            'unknown': (128, 128, 128)
        }
        for b in classified:
            color = colors.get(b['type'], (128, 128, 128))
            cv2.line(debug, (b['x'], 0), (b['x'], debug.shape[0]), color, 2)
            # Label
            cv2.putText(debug, b['type'][:3], (b['x']-15, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        crop_path = f'{out_dir}/sys-{si}.png'
        cv2.imwrite(crop_path, debug)

        # Summary
        barlines_x = [b['x'] for b in classified]
        type_str = ', '.join(f"{b['type']}@{b['x']}" for b in classified)
        print(f"  System {si}: {n_meas} measures | {type_str}")

        sys_info = {
            'system_idx': si,
            'crop_path': os.path.abspath(crop_path),
            'y0_page': s_top,
            'y1_page': s_bot,
            'first_staff_top': first_staff['top'],
            'stave_count': len(sys_staves),
            'staves': [
                {'top': s['top'], 'bot': s['bot'], 'line_count': s.get('line_count', 5)}
                for s in sys_staves
            ],
            'num_measures': n_meas,
            'barlines': [
                {
                    'type': b['type'],
                    'x': b['x'],
                    'num_lines': b['num_lines'],
                    'dots_left': b['dots_left'],
                    'dots_right': b['dots_right']
                }
                for b in classified
            ],
            'measure_gaps': measure_gaps
        }
        result['systems'].append(sys_info)

    # Save JSON
    json_path = f'{out_dir}/structure.json'
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Saved to {json_path}")
    return result

if __name__ == '__main__':
    pn = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    detect_page(pn)
