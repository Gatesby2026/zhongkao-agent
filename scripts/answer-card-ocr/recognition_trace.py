#!/usr/bin/env python3
"""选择题识别"逐题 trace" —— 界面可视化 + pipeline 共用的数据底座。

把两路独立信源合流成每题一条 trace：
  · 像素探针 (pixel_probe)  —— model-free 黑度回投，主信源
  · 缺字母    (OCR ocr_missing) —— 唯一缺一个字母时即读取器答案
共识 → status(green/yellow/red) + reason + conf，给界面叠标注 / 给 pipeline 定不确定集。

输出 schema（每题）:
  {qid, final, conf, status, reason,
   probe:{pred, margin, dens:{A,B,C,D}},
   reader:{method:"缺字母", pred|null, missing:[...]}}

green = 探针高置信且不与读取器冲突 → 自动采纳
yellow= 探针 vs 读取器分歧 / margin 偏低 → 界面标黄请用户确认
red   = 疑似未涂 / 多格黑度接近无法判定 → 转手工录入
"""
import sys, json
from pathlib import Path
sys.path.insert(0, 'scripts/answer-card-ocr')
from pixel_probe import probe

# 阈值（待多卡标定，见 doc §4.1.1 待硬化）
BLANK_DENS = 0.10   # 最黑格都低于此 → 疑似未作答
TIE_MARGIN = 0.06   # margin 低于此 → 多格接近，无法判定
LOW_MARGIN = 0.12   # margin 低于此 → 标黄


def consensus(pred, margin, dens, ocr_missing):
    top_dens = dens.get(pred, 0.0)
    reader = ocr_missing[0] if len(ocr_missing) == 1 else None  # 唯一缺字母才算读取器有效答案
    agree = reader is not None and reader == pred
    disagree = reader is not None and reader != pred

    if top_dens < BLANK_DENS:
        status, reason = 'red', f'最黑格黑度仅 {top_dens:.2f}，疑似未作答/未检出涂卡'
    elif margin < TIE_MARGIN:
        status, reason = 'red', f'多格黑度接近（margin {margin:.2f}），无法判定'
    elif disagree:
        status, reason = 'yellow', f'像素判 {pred} 但缺字母指向 {reader}，两源分歧'
    elif margin < LOW_MARGIN:
        status, reason = 'yellow', f'像素 margin 偏低（{margin:.2f}），建议确认'
    elif agree:
        status, reason = 'green', '像素 + 缺字母一致'
    else:
        status, reason = 'green', f'像素高置信（margin {margin:.2f}）'

    if status == 'green':
        conf = round(min(0.99, 0.6 + margin + (0.1 if agree else 0)), 2)
    elif status == 'yellow':
        conf = round(min(0.6, 0.3 + margin), 2)
    else:
        conf = round(min(0.3, top_dens), 2)
    return status, reason, conf, reader


def build_trace(image_path):
    raw = probe(image_path)
    questions = []
    for qid in sorted(raw):
        v = raw[qid]
        pred, margin, dens = v['pred'], v['margin'], v['dens']
        missing = v['ocr_missing']
        status, reason, conf, reader = consensus(pred, margin, dens, missing)
        questions.append({
            'qid': qid,
            'final': pred,
            'conf': conf,
            'status': status,
            'reason': reason,
            'probe': {'pred': pred, 'margin': margin, 'dens': dens,
                      'cells': v.get('cells', {}), 'h': v.get('h', 0),
                      'page': Path(image_path).name},
            'reader': {'method': '缺字母', 'pred': reader, 'missing': missing},
            'tiebreak': None,
        })
    summ = {'total': len(questions),
            'green': sum(q['status'] == 'green' for q in questions),
            'yellow': sum(q['status'] == 'yellow' for q in questions),
            'red': sum(q['status'] == 'red' for q in questions)}
    summ['need_review'] = [q['qid'] for q in questions if q['status'] != 'green']
    return {'questions': questions, 'summary': summ}


_TIEBREAK_PROMPT = (
    "这是一道单选题的填涂区，水平排列着 A、B、C、D 四个选项框。"
    "请判断学生用铅笔或黑笔涂黑(填涂)了哪一个选项。"
    "只看哪个被明显涂黑，不要根据对错猜测。"
    "若无法确定或四个都没涂，输出空字符串。"
    '严格返回 JSON：{"filled":"A"} 或 {"filled":""}。'
)


def vlm_tiebreak(trace, detect_map, photos_dir, single_choice_qnums, cap=12):
    """对"探针 vs 识别分歧"的单选题做 VLM 逐题放大打平局。

    detect_map: {qnum:int -> letter:str}（识别/Method D 给的单字母答案）
    保守纠正：仅当 **探针 与 VLM 放大两源一致且 != 识别** 才覆盖识别。
    返回 (corrections:{qnum->letter}, n_disagree:int)。
    """
    from PIL import Image, ImageOps
    import vlm_choice

    sc = set(single_choice_qnums)
    cand = []
    if trace.get('aligned'):
        for q in trace['questions']:
            qn = q['qid']
            d = detect_map.get(qn, '')
            p = q['final']
            if qn in sc and d and p and d != p and q['status'] != 'red':
                cand.append(q)
    corrections = {}
    if not cand or len(cand) > cap:   # 无分歧 / 大面积崩盘(交门禁兜底)
        return corrections, len(cand)

    client = vlm_choice._client()
    cache = {}
    for q in cand:
        cells = q['probe'].get('cells') or {}
        page = q['probe'].get('page')
        if len(cells) < 4 or not page:
            continue
        if page not in cache:
            cache[page] = ImageOps.exif_transpose(
                Image.open(Path(photos_dir) / page)).convert('RGB')
        im = cache[page]
        xs = [c[0] for c in cells.values()]
        cy = cells['A'][1]
        h = q['probe'].get('h') or 30
        step = (max(xs) - min(xs)) / 3 if len(xs) > 1 else 40
        box = (max(0, int(min(xs) - step)), max(0, int(cy - h * 1.6)),
               min(im.width, int(max(xs) + step)), min(im.height, int(cy + h * 1.6)))
        crop = im.crop(box)
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
        try:
            data = vlm_choice._call(client, crop, _TIEBREAK_PROMPT, max_tokens=64)
        except Exception:
            continue
        v = str(data.get('filled', '')).strip().upper()[:1]
        d, p = detect_map.get(q['qid'], ''), q['probe']['pred']
        if v == p and v != d:                      # 探针+VLM 两源压识别 → 纠正
            q['final'], q['status'], q['conf'] = v, 'green', 0.9
            q['reason'] = f'探针+VLM放大一致({v})，纠正识别({d})'
            q['tiebreak'] = {'vlm': v, 'result': 'override'}
            corrections[q['qid']] = v
        elif v == d:                                # VLM 支持识别 → 维持
            q['final'], q['status'], q['conf'] = d, 'green', 0.85
            q['reason'] = f'VLM放大支持识别({d})'
            q['tiebreak'] = {'vlm': v, 'result': 'confirm'}
        else:                                       # 三方各执一词 → 留人工
            q['reason'] = f'三方分歧(探针{p}/识别{d}/VLM{v or "?"})，建议人工'
            q['tiebreak'] = {'vlm': v, 'result': 'unresolved'}

    qs = trace['questions']
    trace['summary'] = {
        'total': len(qs),
        'green': sum(x['status'] == 'green' for x in qs),
        'yellow': sum(x['status'] == 'yellow' for x in qs),
        'red': sum(x['status'] == 'red' for x in qs),
        'need_review': [x['qid'] for x in qs if x['status'] != 'green']}
    return corrections, len(cand)


def build_trace_pages(image_paths):
    """多页：逐页跑探针（页级 try/except 容错），题号跨页连续 1..N。"""
    questions = []
    for p in image_paths:
        try:
            sub = build_trace(p)['questions']
        except Exception as e:  # 单页失败不拖垮整卷
            print(f"[recognition_trace] 跳过 {p}: {e}", file=sys.stderr)
            continue
        for q in sub:
            q = dict(q); q['qid'] = len(questions) + 1
            questions.append(q)
    summ = {'total': len(questions),
            'green': sum(q['status'] == 'green' for q in questions),
            'yellow': sum(q['status'] == 'yellow' for q in questions),
            'red': sum(q['status'] == 'red' for q in questions)}
    summ['need_review'] = [q['qid'] for q in questions if q['status'] != 'green']
    return {'questions': questions, 'summary': summ, 'aligned': False}


def align_to_qnums(trace, qnums):
    """把探针顺序题号(1..N)重映射到真实题号。仅当数量相等才映射，否则标 aligned=False。"""
    qs = trace.get('questions', [])
    qnums = sorted(qnums)
    if len(qs) == len(qnums) and qnums:
        for q, n in zip(qs, qnums):
            q['qid'] = n
        trace['aligned'] = True
    else:
        trace['aligned'] = False
    # need_review 用映射后题号
    trace.setdefault('summary', {})['need_review'] = [
        q['qid'] for q in qs if q['status'] != 'green']
    return trace


if __name__ == '__main__':
    path = sys.argv[1]
    out = build_trace(path)
    if '--json' in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        s = out['summary']
        print(f"共 {s['total']} 题  🟢{s['green']}  🟡{s['yellow']}  🔴{s['red']}"
              f"  待确认: {s['need_review']}")
        print('-' * 72)
        for q in out['questions']:
            icon = {'green': '🟢', 'yellow': '🟡', 'red': '🔴'}[q['status']]
            d = q['probe']['dens']
            print(f"Q{q['qid']:<2} {icon} {q['final']}  conf={q['conf']:.2f}  "
                  f"A/B/C/D={d.get('A',0):.2f}/{d.get('B',0):.2f}/{d.get('C',0):.2f}/{d.get('D',0):.2f}"
                  f"  | {q['reason']}")
