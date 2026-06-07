#!/usr/bin/env python3
"""选择题"像素回投"探针 (model-free)。

思路：腾讯 OCR 定位"没涂的字母"bbox → 用字母身份+步距反推每题 4 个选项格的坐标
（含被涂黑、OCR 漏读的那个）→ 在每个格子量黑度 → 最黑的=涂的；
margin=(最黑-次黑) 当置信度。完全不依赖任何"读"的模型，是 VLM 的独立证伪源。
"""
import sys, statistics
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
sys.path.insert(0, 'scripts/answer-card-ocr')
from tencent_choice_grid import _ocr_letters, _cluster_rows, _filter_choice_rows


def grid_from_row(row):
    """一行 letters → 切成题（3×letter_step 分组）→ 每题反推 A-D 四格中心 x。"""
    xs = sorted(row, key=lambda L: L['cx'])
    gaps = [xs[i+1]['cx'] - xs[i]['cx'] for i in range(len(xs)-1)]
    small = [g for g in gaps if g <= (statistics.median(gaps) if gaps else 0)]
    step = statistics.median(small) if small else (statistics.median(gaps) if gaps else 40)
    thr = step * 3
    # 分题
    qs, cur = [], [xs[0]]
    for L in xs[1:]:
        if L['cx'] - cur[-1]['cx'] <= thr:
            cur.append(L)
        else:
            qs.append(cur); cur = [L]
    qs.append(cur)
    out = []
    for q in qs:
        # 用任一已知字母 + 身份反推 A 的 x：A_x = cx - (ord-65)*step
        anchors = [L['cx'] - (ord(L['letter']) - 65) * step for L in q]
        ax = statistics.median(anchors)
        cy = int(statistics.median([L['cy'] for L in q]))
        h = int(statistics.median([L['y2'] - L['y1'] for L in q]))
        cells = {chr(65+i): (int(ax + i*step), cy) for i in range(4)}
        seen = {L['letter'] for L in q}
        out.append({'cells': cells, 'cy': cy, 'h': h, 'step': step,
                    'ocr_seen': seen, 'ocr_missing': sorted(set('ABCD') - seen)})
    return out


def black_ratio(arr, cx, cy, bw, bh, thr=110):
    H, W = arr.shape
    x1, x2 = max(0, cx-bw//2), min(W, cx+bw//2)
    y1, y2 = max(0, cy-bh//2), min(H, cy+bh//2)
    sub = arr[y1:y2, x1:x2]
    return float((sub < thr).mean()) if sub.size else 0.0


def probe(image_path, n_expected=8):
    letters = _ocr_letters(Path(image_path))
    rows = _filter_choice_rows(_cluster_rows(letters))
    im = ImageOps.exif_transpose(Image.open(image_path)).convert('L')
    arr = np.asarray(im)
    qid = 1
    res = {}
    for row in rows:
        for g in grid_from_row(row):
            bw = int(g['step'] * 0.85); bh = int(g['h'] * 1.5)
            dens = {L: round(black_ratio(arr, cx, cy, bw, bh), 3)
                    for L, (cx, cy) in g['cells'].items()}
            ranked = sorted(dens.items(), key=lambda kv: -kv[1])
            top, second = ranked[0], ranked[1]
            margin = round(top[1] - second[1], 3)
            res[qid] = {'pred': top[0], 'margin': margin, 'dens': dens,
                        'ocr_missing': g['ocr_missing']}
            qid += 1
    return res


if __name__ == '__main__':
    import json
    path = sys.argv[1]
    truth = sys.argv[2] if len(sys.argv) > 2 else ''
    r = probe(path)
    print(f'Q | 像素pred | margin | 缺字母 | 真值 | dens(A/B/C/D)')
    for q in sorted(r):
        v = r[q]
        miss = ''.join(v['ocr_missing'])
        t = truth[q-1] if truth and q <= len(truth) else '?'
        ok = '✓' if t != '?' and v['pred'] == t else ('✗' if t != '?' else '')
        d = v['dens']
        print(f"Q{q} |   {v['pred']}    | {v['margin']:.3f}  |  {miss:3s}  |  {t}  {ok} | "
              f"{d.get('A',0):.2f}/{d.get('B',0):.2f}/{d.get('C',0):.2f}/{d.get('D',0):.2f}")
