#!/usr/bin/env python3
"""tencent_annotate — 在原页图上画出腾讯 QuestionSplitOCR 切出的每题方框 +
题号 + GroupType + Figure/Option 子框，便于人工核对切题正确性。

用法：
  python3 scripts/exam-ocr/tencent_annotate.py \
      knowledge-original/<series>/<round>/<region>/<subject> --subject physics

输出到 <staging>/annotated/page-NN.png（红框=题外接 / 蓝框=Figure / 绿框=Option）。
直接读 tencent-cache，不重新调 API。
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import derive_out_dir  # noqa: E402

COLORS = {"question": (220, 30, 30), "figure": (30, 100, 230),
          "option": (30, 170, 80), "table": (200, 130, 30)}


def _font(size: int):
    for p in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Helvetica.ttc"):
        try: return ImageFont.truetype(p, size)
        except Exception: pass
    return ImageFont.load_default()


def _bbox(coord, sx, sy):
    if isinstance(coord, list):
        coord = coord[0] if coord else {}
    xs = [coord[k]["X"] for k in ("LeftTop","RightTop","RightBottom","LeftBottom")]
    ys = [coord[k]["Y"] for k in ("LeftTop","RightTop","RightBottom","LeftBottom")]
    return (int(min(xs)*sx), int(min(ys)*sy),
            int(max(xs)*sx), int(max(ys)*sy))


def _peek_num(item):
    q = item.get("Question") or []
    if not q: return None
    m = re.match(r"^\s*(\d{1,2})\s*[.、．]", q[0].get("Text",""))
    return int(m.group(1)) if m else None


def annotate(img_path: Path, cache: dict, out_path: Path):
    img = Image.open(img_path).convert("RGB")
    ow, oh = img.size
    sw, sh = cache.get("_sent_size", [ow, oh])
    sx, sy = ow / sw, oh / sh
    draw = ImageDraw.Draw(img, "RGBA")
    font_big = _font(48)
    font_med = _font(24)
    font_sml = _font(18)

    rl = (cache.get("QuestionInfo") or [{}])[0].get("ResultList", [])
    for idx, item in enumerate(rl):
        # 题外接框
        c = item.get("Coord")
        num = _peek_num(item)
        gt = ""
        q = item.get("Question") or []
        if q:
            gt = q[0].get("GroupType", "")[:6]
        text = q[0].get("Text", "")[:30] if q else ""
        label = f"[{idx}] Q{num}" if num else f"[{idx}] (no#)"
        if gt: label += f" / {gt}"
        if c:
            x1, y1, x2, y2 = _bbox(c, sx, sy)
            draw.rectangle([x1, y1, x2, y2], outline=COLORS["question"], width=5)
            # 标签底色 + 文字
            tb = draw.textbbox((x1, y1-50), label, font=font_big)
            draw.rectangle([tb[0]-4, tb[1]-2, tb[2]+4, tb[3]+2],
                          fill=(255, 255, 0, 220))
            draw.text((x1, y1-50), label, fill=COLORS["question"], font=font_big)
            # stem 摘要
            draw.text((x1+5, y1+5), text, fill=(80, 80, 80), font=font_sml)
        # Figure 子框
        for fi, f in enumerate(item.get("Figure") or []):
            if f.get("Coord"):
                fx1, fy1, fx2, fy2 = _bbox(f["Coord"], sx, sy)
                draw.rectangle([fx1, fy1, fx2, fy2],
                              outline=COLORS["figure"], width=3)
                draw.text((fx1+3, fy1+3), f"fig{fi}",
                         fill=COLORS["figure"], font=font_med)
        # Option 子框
        for oi, o in enumerate(item.get("Option") or []):
            if o.get("Coord"):
                ox1, oy1, ox2, oy2 = _bbox(o["Coord"], sx, sy)
                draw.rectangle([ox1, oy1, ox2, oy2],
                              outline=COLORS["option"], width=2)
                ot = o.get("Text", "")[:4]
                draw.text((ox1+2, oy1+2), ot,
                         fill=COLORS["option"], font=font_sml)
        # Table 子框
        for t in item.get("Table") or []:
            if t.get("Coord"):
                tx1, ty1, tx2, ty2 = _bbox(t["Coord"], sx, sy)
                draw.rectangle([tx1, ty1, tx2, ty2],
                              outline=COLORS["table"], width=3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_dir", type=Path)
    ap.add_argument("--subject", required=True)
    args = ap.parse_args()
    src = args.src_dir.resolve()
    out_dir = derive_out_dir(src)
    cache_dir = out_dir / "tencent-cache"
    ann_dir = out_dir / "annotated"
    pages = sorted((src / "images").glob("page-*.png"))
    for p in pages:
        cf = cache_dir / f"{p.stem}.json"
        if not cf.exists():
            print(f"  {p.name}: 缺 tencent-cache，跳过", flush=True); continue
        cache = json.loads(cf.read_text(encoding="utf-8"))
        out = ann_dir / f"{p.stem}.png"
        annotate(p, cache, out)
        print(f"  → {out}", flush=True)
    # 生成 HTML 索引
    html = ['<html><head><title>Tencent QuestionSplit Review</title>',
            '<style>body{margin:0;background:#222;color:#eee;font-family:sans-serif}',
            'img{max-width:1200px;display:block;margin:20px auto;border:2px solid #555}',
            'h2{text-align:center;margin-top:40px}',
            '.legend{position:fixed;top:10px;right:10px;background:rgba(0,0,0,.8);padding:10px;border-radius:6px;font-size:13px}',
            '.legend span{display:inline-block;width:14px;height:14px;margin-right:5px;vertical-align:middle}',
            '</style></head><body>',
            '<div class="legend">',
            '<div><span style="background:rgb(220,30,30)"></span>题外接框 (红)</div>',
            '<div><span style="background:rgb(30,100,230)"></span>Figure (蓝)</div>',
            '<div><span style="background:rgb(30,170,80)"></span>Option (绿)</div>',
            '<div><span style="background:rgb(200,130,30)"></span>Table (橙)</div>',
            '</div>']
    for p in pages:
        html.append(f'<h2>{p.stem}</h2>')
        html.append(f'<img src="annotated/{p.stem}.png">')
    html.append('</body></html>')
    idx = out_dir / "annotated.html"
    idx.write_text("\n".join(html), encoding="utf-8")
    print(f"\n✅ {idx}")
    # 自动打开
    import subprocess
    subprocess.run(["open", str(idx)])


if __name__ == "__main__":
    main()
