# gaokzx.com 无浏览器 curl 抓取方案

## 关键结论
gaokzx.com 页面全部 SSR 渲染，**curl 可直接访问，无需登录、无需浏览器、无需 JS 执行**。
PDF 直链内嵌在页面第一个含 `zixunzhan` 的 `<script>` JSON 块中（Nuxt SSR 数据）。

## 抓汇总页（获取文章链接列表）

```bash
curl -s -A "Mozilla/5.0" "https://www.gaokzx.com/gk/zhongkao/154872.html" > page.html
# 提取 2026 年二模文章链接（ID > 154000）
grep -oP '/gk/zhongkao/1[5-9]\d{4}\.html' page.html | sort -u
```

## 抓文章页（提取 PDF 直链 + 下载）

```python
import subprocess, json, re, urllib.parse
from pathlib import Path

def fetch_html(url):
    r = subprocess.run(['curl', '-s', '-A', 'Mozilla/5.0', url], capture_output=True, text=True)
    return r.stdout

def extract_pdfs(html):
    """从 NUXT SSR <script> 块中提取 PDF 直链"""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    pdfs = []
    for s in scripts:
        if 'zixunzhan' not in s: continue
        try: data = json.loads(s)
        except: continue
        def walk(obj, depth=0):
            if depth > 15: return
            if isinstance(obj, str) and '.pdf' in obj.lower() and 'cdn.gaokzx.com' in obj:
                pdfs.append(obj)
            elif isinstance(obj, list):
                [walk(x, depth+1) for x in obj]
            elif isinstance(obj, dict):
                [walk(v, depth+1) for v in obj.values()]
        walk(data)
    return list(dict.fromkeys(pdfs))

def download_pdf(pdf_url, out_path):
    """下载 PDF（自动处理 URL 中的中文字符）"""
    encoded = urllib.parse.quote(pdf_url, safe=':/?=&#%')
    subprocess.run(['curl', '-s', '-L', '--output', str(out_path), encoded])

# 示例：下载海淀二模语文
html = fetch_html('https://www.gaokzx.com/gk/zhongkao/155685.html')
pdfs = extract_pdfs(html)
download_pdf(pdfs[0], Path('haidian_chinese.pdf'))
```

## 页面结构说明

- 汇总页（如 154872）：大表格，行 = 区+科目，列 = 2026/2025/2024 年
- 2026 链接特征：ID ≥ 155000（2025 为 140xxx-141xxx，2024 为 shitiku/122xxx）
- 文章页内嵌数据：`cdn.gaokzx.com/zixunzhan/<中文文件名><时间戳>.pdf`
- 文件名含"无答案"/"有答案"标识

## 已用汇总页

| 页面 | 说明 |
|------|------|
| https://www.gaokzx.com/gk/zhongkao/154872.html | 2024-2026 北京初三二模汇总（持续更新） |
| https://www.gaokzx.com/gk/zhongkao/154438.html | 2025-2026 北京初高中各年级热点试题汇总 |
