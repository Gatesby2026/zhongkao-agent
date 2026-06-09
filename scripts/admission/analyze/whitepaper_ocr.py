#!/usr/bin/env python3
"""OCR《2026 高中指南白皮书·朝阳区》第三章 26 所公办高中档案的"往年成绩"数据页。
qwen-vl-max 逐页 OCR + 逐页缓存(.cache/whitepaper_ocr.json),抽录取线+高考成绩用。
印刷页 + 10 = PDF 1-based 页;数据页通常在档案 start+1(学校概况之后)。
"""
import base64
import concurrent.futures as cf
import json
import os
import urllib.request
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "knowledge-original/zhiyuan/2026 高中指南白皮书 朝阳区.pdf"
CACHE = ROOT / ".cache/whitepaper_ocr.json"
OUT = ROOT / "knowledge-base/admission/beijing/raw_extracts/whitepaper_ocr_raw.json"
KEY = os.environ.get("DASHSCOPE_API_KEY", "")

# 校名 → 档案首页(印刷页);PDF 1-based = 印刷 + 10。和平街校区并入和平街一中。
SCHOOLS = {
    "北京中学": 114, "清华附中朝阳学校": 118, "人大附中朝阳学校": 122,
    "北京市第八十中学": 126, "陈经纶中学": 131, "北京工业大学附属中学": 135,
    "日坛中学": 139, "和平街一中": 143, "对外经济贸易大学附属中学": 148,
    "东北师大附中朝阳学校": 152, "朝阳外国语学校": 156, "清华附中望京学校": 160,
    "二中朝阳学校": 163, "三里屯一中": 166, "中科院附属实验学校": 169,
    "北京第二外国语学院附属中学": 173, "北京化工大学附属中学": 176,
    "陈经纶中学团结湖分校": 179, "首师大附中朝阳学校": 182, "汇文中学垂杨柳分校": 185,
    "清华附中广华学校": 191, "中国传媒大学附属中学": 194, "八十中睿德分校": 197,
    "北京十七中": 200, "东方德才学校": 203, "北京中学科技分校": 206,
}
# 每校 OCR 的 PDF 页偏移(相对印刷页+10):概况(0)+数据页(1)+备份(2)。数据多在 +1。
OFFSETS = [0, 1, 2]


def load_cache():
    return json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {}


def ocr_page(doc, idx):
    pix = doc[idx].get_pixmap(dpi=170)
    b64 = base64.b64encode(pix.tobytes("png")).decode()
    body = json.dumps({"model": "qwen-vl-max", "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        {"type": "text", "text": "完整提取本页所有文字,含节标题(如'三、往年成绩')、表格(逐行逐列含数字)、分数线与排名、高考成绩。原样输出,保留表格结构,不要总结。"}]}]}).encode()
    req = urllib.request.Request("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                                 data=body, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=150))["choices"][0]["message"]["content"]


def main():
    assert KEY, "需 DASHSCOPE_API_KEY"
    doc = fitz.open(PDF)
    cache = load_cache()
    # 收集所有要 OCR 的 PDF 0-based 页号
    pages = {}   # idx -> None
    for name, printed in SCHOOLS.items():
        base = printed + 10 - 1   # 0-based
        for off in OFFSETS:
            pages[base + off] = True
    todo = [idx for idx in pages if str(idx) not in cache]
    print(f"共需 {len(pages)} 页, 已缓存 {len(pages)-len(todo)}, 待 OCR {len(todo)}")

    def work(idx):
        try:
            return idx, ocr_page(doc, idx)
        except Exception as e:
            return idx, f"__ERR__ {repr(e)[:150]}"

    if todo:
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for idx, txt in ex.map(work, todo):
                cache[str(idx)] = txt
                tag = "✗" if txt.startswith("__ERR__") else "✓"
                print(f"  {tag} PDF p{idx+1}")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 按校汇总 OCR 文本(拼 3 页)→ raw json,供解析步骤
    per_school = {}
    for name, printed in SCHOOLS.items():
        base = printed + 10 - 1
        texts = []
        for off in OFFSETS:
            t = cache.get(str(base + off), "")
            texts.append({"pdf_page": base + off + 1, "text": t})
        per_school[name] = {"printed_start": printed, "pages": texts}
    json.dump(per_school, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    errs = sum(1 for v in cache.values() if v.startswith("__ERR__"))
    print(f"写 {OUT.name}: {len(per_school)} 校 (OCR 错误页 {errs})")


if __name__ == "__main__":
    main()
