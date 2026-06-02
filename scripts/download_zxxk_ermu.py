#!/usr/bin/env python3
"""自动从学科网下载 2026 北京二模 52 份资料，移动到 knowledge-original/zxxk-downloads/"""

import subprocess, time, os, shutil, re, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_BASE = ROOT / "knowledge-original/zxxk-downloads"

# 52 entries: (district_en, subject_en, subject_cn, softId, is_boutique)
ENTRIES = [
    ("changping",   "chinese",  "语文",  "58104300",  False),
    ("changping",   "english",  "英语",  "58117308",  True),
    ("changping",   "math",     "数学",  "58077655",  True),
    ("changping",   "physics",  "物理",  "58128865",  False),
    ("changping",   "politics", "道法",  "58124957",  True),
    ("chaoyang",    "chinese",  "语文",  "58049196",  False),  # already downloaded
    ("chaoyang",    "english",  "英语",  "58103285",  True),
    ("chaoyang",    "math",     "数学",  "58076096",  False),
    ("chaoyang",    "physics",  "物理",  "58108085",  True),
    ("chaoyang",    "politics", "道法",  "58119358",  True),
    ("daxing",      "chinese",  "语文",  "58100846",  False),
    ("daxing",      "english",  "英语",  "58120147",  False),
    ("daxing",      "math",     "数学",  "58091471",  False),
    ("daxing",      "physics",  "物理",  "58126668",  True),
    ("daxing",      "politics", "道法",  "58125873",  True),
    ("fangshan",    "chinese",  "语文",  "58061067",  False),
    ("fangshan",    "english",  "英语",  "58115234",  True),
    ("fangshan",    "math",     "数学",  "58084112",  False),
    ("fangshan",    "physics",  "物理",  "58126776",  True),
    ("fangshan",    "politics", "道法",  "58119110",  False),
    ("fengtai",     "chinese",  "语文",  "58101753",  False),
    ("fengtai",     "english",  "英语",  "58129336",  True),
    ("fengtai",     "math",     "数学",  "58126664",  False),
    ("fengtai",     "physics",  "物理",  "58116637",  False),
    ("fengtai",     "politics", "道法",  "58120358",  False),
    ("haidian",     "chinese",  "语文",  "58069884",  False),  # already downloaded
    ("haidian",     "math",     "数学",  "58128584",  True),   # already downloaded
    ("haidian",     "physics",  "物理",  "58124494",  True),
    ("haidian",     "politics", "道法",  "58110075",  True),
    ("mentougou",   "english",  "英语",  "57685133",  True),
    ("mentougou",   "math",     "数学",  "57680013",  True),
    ("pinggu",      "chinese",  "语文",  "58061232",  False),
    ("pinggu",      "english",  "英语",  "58123899",  False),
    ("pinggu",      "math",     "数学",  "58102014",  False),
    ("pinggu",      "physics",  "物理",  "58124702",  True),
    ("shijingshan", "chinese",  "语文",  "58116522",  False),
    ("shijingshan", "english",  "英语",  "58126860",  False),
    ("shijingshan", "math",     "数学",  "58095436",  False),
    ("shijingshan", "physics",  "物理",  "58118691",  False),
    ("shijingshan", "politics", "道法",  "58120339",  False),
    ("shunyi",      "chinese",  "语文",  "58107406",  False),
    ("shunyi",      "english",  "英语",  "58118657",  True),
    ("shunyi",      "math",     "数学",  "58126420",  False),
    ("shunyi",      "physics",  "物理",  "58124010",  False),
    ("shunyi",      "politics", "道法",  "58121529",  False),
    ("xicheng",     "chinese",  "语文",  "58072409",  True),
    ("xicheng",     "english",  "英语",  "58081350",  True),
    ("xicheng",     "math",     "数学",  "58090532",  True),
    ("xicheng",     "physics",  "物理",  "58060206",  False),
    ("xicheng",     "politics", "道法",  "58064990",  True),   # already downloaded
    ("yanshan",     "math",     "数学",  "58107250",  True),
    ("yanshan",     "politics", "道法",  "58120308",  False),
]

DOWNLOADS_DIR = Path.home() / "Downloads"


def run_js(js: str) -> str:
    """Execute JS in Chrome's active tab via AppleScript.
    Uses double-quoted AppleScript string; any double-quotes in js must be escaped."""
    # Escape backslashes, double-quotes, and newlines for AppleScript string literal
    safe_js = js.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')
    script = f'tell application "Google Chrome"\n  execute active tab of front window javascript "{safe_js}"\nend tell'
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def get_current_url() -> str:
    script = 'tell application "Google Chrome"\n  return URL of active tab of front window\nend tell'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def navigate(url: str, wait: float = 5.0):
    """Navigate Chrome to url, verify it loaded, retry if needed."""
    for attempt in range(4):
        # Use explicit double-quote string (NOT repr() which uses single quotes = AppleScript syntax error)
        script = f'tell application "Google Chrome"\n  set URL of active tab of front window to "{url}"\nend tell'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        # Wait for page to load and verify URL changed
        time.sleep(2)  # let any conflicting navigation settle first
        deadline = time.time() + wait
        while time.time() < deadline:
            time.sleep(0.8)
            current = get_current_url()
            if url in current or current.endswith(url.split("/")[-1].split("?")[0]):
                # Also wait for readyState = complete
                time.sleep(1.0)
                return True
        print(f"     ⚠️  Navigation attempt {attempt+1}: still on {get_current_url()[:60]}")


def wait_for_download(before_files: set, timeout: int = 60):  # -> Path or None
    """Wait for a new non-.crdownload file to appear in Downloads."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Wait until no .crdownload files
        crfiles = set(glob.glob(str(DOWNLOADS_DIR / "*.crdownload")))
        current = set(glob.glob(str(DOWNLOADS_DIR / "*")))
        new_files = current - before_files - crfiles
        if new_files and not crfiles:
            return Path(sorted(new_files, key=os.path.getmtime)[-1])
        time.sleep(1)
    return None


def get_out_path(district_en: str, subject_en: str, is_boutique: bool, soft_id: str) -> Path:
    label = "boutique" if is_boutique else "plain"
    out_dir = OUT_BASE / f"2026-ermu-{subject_en}"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{district_en}_{subject_en}"  # extension added later


def already_done(district_en: str, subject_en: str) -> bool:
    out_dir = OUT_BASE / f"2026-ermu-{subject_en}"
    for ext in (".docx", ".zip", ".doc"):
        if (out_dir / f"{district_en}_{subject_en}{ext}").exists():
            return True
    return False


def verify_page(soft_id: str) -> dict:
    """Pre-download checks: confirm page exists, is 精品解析, has answers.
    Returns dict with keys: ok(bool), boutique(bool), title(str), warning(str).
    """
    import zipfile
    title_js = "document.title"
    body_js = "document.body ? document.body.innerText.slice(0,800) : ''"
    title = run_js(title_js)
    body  = run_js(body_js)

    # Check resource exists (page not redirected to homepage)
    no_btns = run_js("document.querySelectorAll('#btnSoftDownload').length") == "0"
    default_title = "学科网-海量中小学教育资源共享平台" in title
    if default_title or no_btns:
        return {"ok": False, "boutique": False, "title": title,
                "warning": "资源不存在或已下架（页面无下载按钮）"}

    # Check 精品解析 (guaranteed to have answers)
    is_boutique_page = "精品解析" in title or "精品解析" in body
    # Also accept if body clearly mentions 答案/解析
    has_answer_hint = any(kw in body for kw in ["【答案】", "答案解析", "解题过程", "参考答案"])

    if not is_boutique_page and not has_answer_hint:
        return {"ok": True, "boutique": False, "title": title,
                "warning": "⚠️  非精品解析 且页面无答案迹象 — 可能缺答案"}

    return {"ok": True, "boutique": is_boutique_page, "title": title, "warning": ""}


def verify_downloaded_file(dl_file: Path) -> dict:
    """Post-download checks: confirm real DOC format (not bare PDF).
    Returns dict: ok(bool), ext(str), has_docx(bool), warning(str).
    """
    import zipfile
    ext = dl_file.suffix.lower()
    if not ext:
        ext = ".zip"

    if ext == ".pdf":
        return {"ok": False, "ext": ext, "has_docx": False,
                "warning": "❌ 文件是 PDF 格式，不是 DOC/DOCX"}

    if ext in (".docx", ".doc"):
        return {"ok": True, "ext": ext, "has_docx": True, "warning": ""}

    if ext == ".zip":
        try:
            with zipfile.ZipFile(dl_file) as zf:
                names = zf.namelist()
            has_docx = any(n.lower().endswith((".docx", ".doc")) for n in names)
            if not has_docx:
                return {"ok": False, "ext": ext, "has_docx": False,
                        "warning": f"❌ ZIP 内无 docx/doc（内含: {names[:3]}）"}
            return {"ok": True, "ext": ext, "has_docx": True, "warning": ""}
        except Exception as e:
            return {"ok": False, "ext": ext, "has_docx": False,
                    "warning": f"❌ ZIP 解析失败: {e}"}

    # Unknown extension — warn but allow
    return {"ok": True, "ext": ext, "has_docx": False,
            "warning": f"⚠️  未知格式 {ext}，请人工核查"}


def download_one(district_en: str, subject_en: str, subject_cn: str,
                 soft_id: str, is_boutique: bool) -> bool:
    url = f"https://www.zxxk.com/soft/{soft_id}.html"
    print(f"\n  🔄 {district_en} {subject_cn} ({'精品' if is_boutique else '普通'}) id={soft_id}")

    # Snapshot current Downloads
    before = set(glob.glob(str(DOWNLOADS_DIR / "*")))

    # Allow any pending Chrome navigation (softdownload page) to settle first
    time.sleep(3)

    # Navigate
    navigate(url)
    time.sleep(2)  # additional settle time after navigation

    # ── 验证 1：下载前核查（精品解析 + 有答案）──────────────────────────
    page_check = verify_page(soft_id)
    print(f"     📋 页面: {page_check['title'][:60]}")
    if not page_check["ok"]:
        print(f"     ❌ 跳过: {page_check['warning']}")
        return False
    if page_check["warning"]:
        print(f"     {page_check['warning']}")
        # Continue but flag it (non-boutique may still have answers)
    elif page_check["boutique"]:
        print(f"     ✅ 精品解析确认")
    # ──────────────────────────────────────────────────────────────────────

    # Find and click the VIP储值 button
    btn_js = """
var btns = Array.from(document.querySelectorAll('#btnSoftDownload'));
var vip = btns.find(function(b){ return b.innerText.indexOf('储值') >= 0; });
if(vip){ vip.click(); 'clicked'; } else { 'no_vip_btn'; }
"""
    result = run_js(btn_js)
    if "no_vip_btn" in result:
        print(f"     ⚠️  No VIP button — might be free or already purchased")
        # Try plain download button
        run_js("var b = document.querySelectorAll('#btnSoftDownload')[0]; b && b.click();")
        time.sleep(3)
    else:
        time.sleep(2.5)

    # Check for payment dialog and click confirm
    confirm_js = """
var dlg = document.getElementById('layui-layer-iframe2');
if(dlg && dlg.contentDocument){
  var btn = dlg.contentDocument.querySelector('.balance-payment-btn');
  if(btn){ btn.click(); 'confirmed'; } else { 'no_confirm_btn'; }
} else { 'no_dialog'; }
"""
    confirm_result = run_js(confirm_js)
    if "no_dialog" in confirm_result:
        print(f"     ⚠️  No payment dialog — checking if download started anyway")
    elif "confirmed" in confirm_result:
        print(f"     💳 Payment confirmed")
    else:
        print(f"     ⚠️  Confirm result: {confirm_result}")

    # Wait for download
    dl_file = wait_for_download(before, timeout=45)
    if not dl_file:
        print(f"     ❌ No download appeared within 45s")
        return False

    # ── 验证 2：下载后核查（真 DOC 格式）────────────────────────────────
    file_check = verify_downloaded_file(dl_file)
    if file_check["warning"]:
        print(f"     {file_check['warning']}")
    if not file_check["ok"]:
        print(f"     ❌ 文件格式不合格，跳过移动（保留在 Downloads: {dl_file.name}）")
        return False
    # ──────────────────────────────────────────────────────────────────────

    ext = file_check["ext"]
    # Move to destination
    out_dir = OUT_BASE / f"2026-ermu-{subject_en}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{district_en}_{subject_en}{ext}"
    shutil.move(str(dl_file), str(dest))
    size_kb = dest.stat().st_size // 1024
    print(f"     ✅ Saved {dest.name} ({size_kb}KB)")
    return True


def main():
    ok = skip = fail = 0

    for district_en, subject_en, subject_cn, soft_id, is_boutique in ENTRIES:
        if already_done(district_en, subject_en):
            print(f"  ✅ skip  {district_en}_{subject_en} (already exists)")
            skip += 1
            continue

        success = False
        for attempt in range(2):
            try:
                success = download_one(district_en, subject_en, subject_cn, soft_id, is_boutique)
                if success:
                    break
            except Exception as e:
                print(f"     ❌ Error attempt {attempt+1}: {e}")
            if not success and attempt == 0:
                print(f"     🔁 Retrying...")
                time.sleep(3)

        if success:
            ok += 1
        else:
            fail += 1

        time.sleep(1.5)  # brief pause between files

    print(f"\n📊 Done: {ok} downloaded, {skip} skipped, {fail} failed")


if __name__ == "__main__":
    main()
