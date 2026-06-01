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
DOT_DISTANCE = 35    # px: max distance from compound center to look for dots
DOT_MIN_AREA = 20
DOT_MAX_AREA = 120

def detect_dots(gray_segment, x_center, staff_ys):
    """Detect small round blobs near x_center within staff y-ranges."""
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

        # Size filter: small but not tiny
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
    if is_last_group:
        return 'system_end'

    # Single line
    if n == 1:
        return 'thin'

    # Multi-line: check for repeat dots FIRST
    gx = (lines[0]['x'] + lines[-1]['x']) // 2
    left_dots = [d for d in dots_rel if d['x'] < gx]
    right_dots = [d for d in dots_rel if d['x'] >= gx]
    has_left = len(left_dots) >= 2
    has_right = len(right_dots) >= 2

    if has_left and has_right:
        return 'end_start_repeat'
    elif has_right:
        return 'start_repeat'
    elif has_left:
        return 'end_repeat'

    # Check for thick line (final barline = thin+thick)
    # In standard notation, final barline has thin on left, thick on right
    last_thick = lines[-1].get('thickness', 1) > 6
    if last_thick:
        return 'final'

    # No dots, no thick → double barline (section boundary)
    if n >= 2:
        return 'double'

    return 'unknown'

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
    for i in range(len(peaks)-4):
        if i in used: continue
        t = peaks[i]
        expected = [(t + 19 * (j+1), 3) for j in range(4)]
        found = [t]; pos = i + 1; ok = True
        for exp, tol in expected:
            while pos < len(peaks) and peaks[pos] < exp - tol: pos += 1
            if pos < len(peaks) and abs(peaks[pos] - exp) <= tol:
                found.append(peaks[pos]); used.add(pos); pos += 1
            else: ok = False; break
        if ok:
            staves.append({'top': found[0], 'bot': found[-1]})
            used.add(i)

    # 3-stave systems
    raw_systems = [staves[i:i+3] for i in range(0, len(staves)-2, 3)]
    raw_systems = [s for s in raw_systems if len(s) >= 2]

    print(f"Page {page_num}: {len(raw_systems)} systems, {len(staves)} staves")

    result = {'page': page_num, 'systems': []}

    for si, sys_staves in enumerate(raw_systems):
        vocal = sys_staves[0]
        s_top = max(0, vocal['top'] - 90)
        s_bot = min(h, sys_staves[-1]['bot'] + 30)
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
        # Number of measures = number of gaps between consecutive classified barlines
        # With N classified barlines, there are N-1 gaps (= measures)
        # crop_measures.py handles clef area removal separately
        n_meas = len(classified) - 1

        # The first real barline = end of measure 1
        # For proper crop: measures span from prev_barline.x to current_barline.x

        # Build measure boundaries array
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
            'vocal_staff_top': vocal['top'],
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
            ]
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
