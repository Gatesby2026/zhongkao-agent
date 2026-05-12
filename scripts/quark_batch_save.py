#!/usr/bin/env python3
"""
夸克网盘批量转存脚本
结构: 初中教辅资源 / 科目 / 出版社 / 版本 / 年份
"""
import urllib.request, urllib.parse, urllib.error, json, time, re, openpyxl, ssl
from collections import defaultdict

# ============================
# 配置区（敏感信息）
# ============================
COOKIE = 'xlly_s=1; b-user-id=6c5d8dfa-9524-b701-7c58-33a80f36e1c7; __sdid=AAROoD0vCTNAcRDTkkKhbie1ICs60AvLO4UAKa2piyMjDrfqbKDQns1QVuev8oq9uYQ1VcAmgQAsyaCQtyJlPJljoBJ2dyXD9ca0Kcn824h5sA==; _UP_D_=pc; _UP_A4A_11_=wba2c1ddd07c400e96406b954991ffc7; __pus=2777d852a5a524346973aa3965f593c5AASEvDp7oLND5F456l3Hq7k8wrbEesF2Q5//ksBuEj/+bcmtRRFDlbNkr7SFAqiq9oOdKW3iagK80lF/dqRpDd3V; __kp=c4107920-3802-11f1-8cad-b91d24435a40; __kps=AAS0xpSHwwNbvZa/j7vfhDtX; __ktd=fGoGYcowO31Qhbo/nh8WoA==; __uid=AAS0xpSHwwNbvZa/j7vfhDtX; __puus=14658198edb401c047e09ed7470a6c41AAS7SLUyX2e6o083Ld+jxTk8nYNtlw4qKzMH/W6EaDMKH4hhAikVpUcBmfQZ7iNX4bCHelG4PE+ZG3EfTLdxXbFBQLUJbdxEADnzg+aY20PossVGo1oX7sMbTWrZQQi7l9A/pocWBESdQfjOiICTNKS58OsTlZ5ovzDDfTfFE1gNH/TAFm4FerDuw5QOQ2Bcunfi8X8nkZU4mAN0MWsHiQhw; tfstk=gdpiDYm01wa5WHaEErWs9jyKZZhpCO6fREeAktQqTw7Ckctv0ty2knBOgVtv-Z7ekSRAuG5c8UYjc-5ZSemDWnwA7NpAns8RQsOOkNQcnnTov4H-eht1ht3-yY3HkU2cFSrN7reFTg6cb5ckr-K1htu8v-l-EhTTOonc_tohLijlbt5N3MohXiB4QsyaTy7C0tWVu17F8gszuGyVuDxFRiWVuE5Zx97C0t72utlTZ5763dpEzAV7yCbbgdSGsa-N7hK9Lofa1HQ33-8et1brew243pjM0lpX0Rkl8Cd2B9JZ8rWeVBLNxTDgPGAeqefJpyeAUQTHn_WoMc6yCnRWghDnzOp6bQ52UqN2fO7GaQ8x07bXvQf2w6ziJZdJvd5Hz2eHlsA2B9JZ8zbX6g6h4yPUaYoQhMovLSNf_Mshy8jhcN4cIUX-xDVo_1SCABnnxSNf_MshyDm3Zf5NAMOd.; isg=BDQ0ZILm4bgwA3V1RdvcJEWOBfSmDVj34skM_c6VBL9COdaD9h-dhea7vVHhwZBP'

BX_UA = '231\u0021UlB3qAmU7Nv+jmlDu47mYKDjUGg0uSOn+fOSk+rou4DaIpSH/4rFBxXBdWVH/4OmBkPLH+4lDtyNnMy0rXrK7gWEL5ZgeFlGUaBYEMcfcBf+277nKnXmRy78gHYZxA5PgKattb6+xx9toCpHaJFkTeSnBstKqkNryKKRSKjX63lg/jxrHFMtpYRT9+IXGj+LSn8nel+Xb4gYDkoEHAbWQOp2/wiIayilE2Ayt9txSSLcGHby+Q16AM1cOowsSnCsPBMn3ko50Q/oyk8jauHhUAIYnpmHH3S+++3+qAS+ZxKn+4mCmp+46bz++ynW+8j09NGwqCz++Ina+4IU1n4+6w4r+KgU++ml9k3+cgSYDIne6AIWYA++GfEj+KFWDwSItgjhFkk3+pFj6Zqy9ZAtcEurL5RPFNLn0JH4ur5Nk8t+p0bnw6Bd/a6pqVE0Uhq7NJ+e3Q60Kumvuid2B58VM91YpvVfWk5zNxjzohIrwzoAQj0FY49qItrg1/FuhEz5m6XSkCDiILIPQ1wPZv7N7Jk/J3vdy/rtCb/Hje70XXHaXw2VTCQC2bnaPbuO8LH73jWuIYuxD44Z1EUeFEXktNrX/C4lJQ2NyaroxKU794f5fi+xSpcylREZ3jwd94nDurXWrhr6FgndoYVbJSyWB97wQxjM+rxBrwQGYs1UkH+f48UlZmmE/Oy942SLCBSx2KvozJiIP8ZzDPDWneXXCaWIjuSnX3AfePI0VmqWd4SjBbO0uuTPEFVnq4rguuFGpK3PfxO21l9QRcSQtb2dVZH9oPwHyj/WShbh2WTnur8zsISAPRZun+7YmFbo+3N2PwSQx4DP/7tG1+Au93lche+k10Y0szScGTnOMV9RE5vwqt7AH8DsbmWcH5P5l6h/ur0uN3z3niwbdN3MdzUA1n7hB2Zy9yYTWKHiMKjfhIMCpa+6xEqzMiMxCaz6XGwKJZG25fE9bdReC/7tNFiHRqsFa7WOyTm3KHvZ4eJM6G/rjmT2FbnxzUz20Ery40LGhh4z/katGHC7/NbrxBo6g6vF6na27+LBCHGtiSuSeFo3iPJ7v5MhsnAR9u6GE5vV+mLJVravLbpxQUKGNrn/xe+OOwo9hyIqbKawkWGaeNVeCh/1RfNxTkQi97wRNjq1YAetCXVUJm3epFrhENPOmNUs9wgwdrEIdjVs3dtR5ftXOgMYlS0LkMBGoWZ71EwWnEAKWmDxBfHE6g/Jfi/n/2Q7AESdAhqILy7bYmSCdOnv4Eay+M3blMtAqxCp6wqwjLC+nZFI1HFEm2cDvTZVUcMw6H3K08fEwJ0LRJAXo+rISejFuun4RcpCdkdu/mminS1bnD9JFW1pWpNdxAuClNc8/MGfIIY97cEp2TadIHmlHYrRUFjhhPVUpRvZnQ6oRTApKkP30zstyDINZ5d7det2nvAQURt+w/rpKn7Z3Rx4IWHy9AhQTk2QNAXzkY1H4/kozE2J8xjJ74WhTQ4D2W7kwsf49WqzDnT6ba6R8Psd/yRm11Tdf8zUdsfaTzARQ8aG5h1edNGMH3GHiIBIWMuIsl/sCGkASlmjotrMgNkrpaUjMER5mjtK91pcln7smAEQmgW5qmxJWHFH3155FsTrfmKDbWxGJVlhxJ8UMuNveF/nFCDkS61C1A6c5fbmk7Cam0C9uBhBe90HQsvwvUx9iqlQ0M0='
BX_UMID = 'T2gALQQnn0gA4ywY2FK_6chZNpvy0uygsaF89NWJ4LL1mPTMeIZHOOl1uQLKVAsWZv0='
BX_ET   = 'gLAqDgtRO1x5GLnH8efZUMS78NfAw1oCmCs1SFYGlijc1xpwUFTEkNtXSGJNqFImWN0Or7xNWdOjBGfl4gxklSs1iG4wfF9XbF3ASGxMbG9jFXTvk1CiA2GIOEIEE03H0N2cqVbC5505nZWEWv1iADGQFzXxc1Yj2RMNZUjR7N2cnhfkrwIuoNxGmTql8wCGjhxGr_bGW5Vgst4lrgQGsGxGs45l2N5GjhfizUcT7hxQaNBmuo2WFiMQGTjHoSgi8yQVnuY4CWNBwaQDsEjPPaOPutShQPUxAB8HoBQw622NbeJDcaKZT05Hp3RNKHm7ahBeII1ki0cheOvMdOJ7m4fGIL9C3Lo0_gOf29RcUumOzLYpXwX4V8KHPeOAeCoUqGpfJ_bw622NbFYp9p1h4SZOrcoB6KrgQtbRzMgrzKeYorPhIkPUBRBfiaSIyWeTBtbRzMgrzReOhsbPA4Fd.'

HEADERS = {
    'Cookie': COOKIE, 'bx-ua': BX_UA, 'bx-umidtoken': BX_UMID, 'bx_et': BX_ET,
    'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://pan.quark.cn/', 'Origin': 'https://pan.quark.cn',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site',
}

EXCEL_PATH   = '/Users/jiakui/projects/zhongkao-agent/knowledge-original/教辅材料/全科AA+初中资源导航.xlsx'
ROOT_NAME    = '初中教辅资源'
TOKEN_HOST   = 'https://drive.quark.cn'
SAVE_HOST    = 'https://drive-h.quark.cn'
DELAY        = 2.0   # 每次请求间隔（秒）
DRY_RUN      = False  # True=只打印计划，不实际操作
PROGRESS_FILE = '/Users/jiakui/projects/zhongkao-agent/scripts/quark_done_ids.json'
LOG_PATH     = '/Users/jiakui/projects/zhongkao-agent/scripts/quark_save_log.json'

# ============================
# 元数据解析
# ============================
SUBJECT_MAP = [
    ('数学', '数学'), ('物理', '物理'), ('英语', '英语'), ('语文', '语文'),
    ('化学', '化学'), ('历史', '历史'), ('道法', '道法'), ('道德与法治', '道法'),
    ('生物', '生物'), ('地理', '地理'), ('政治', '道法'),
    ('语数英', '综合'), ('全科', '综合'),
]
VERSION_MAP = [
    ('人教', '人教版'), ('RJ', '人教版'),
    ('北师大', '北师大版'), ('BSD', '北师大版'), ('BS)', '北师大版'),
    ('外研', '外研版'), ('WY)', '外研版'), ('WL)', '外研版'),
    ('苏科', '苏科版'), ('SK)', '苏科版'),
    ('华师大', '华师大版'), ('HSD', '华师大版'),
    ('浙江', '浙江版'), ('ZJ)', '浙江版'),
    ('北京', '北京版'), ('BJ)', '北京版'),
    ('鲁教', '鲁教版'), ('LJ)', '鲁教版'),
    ('译林', '译林版'), ('YL)', '译林版'),
    ('江苏', '江苏版'), ('JS)', '江苏版'),
]
SKIP_SHEETS = {'目录', '优惠券', 'WpsReserved_CellImgList'}

def parse_subject(title):
    for kw, subj in SUBJECT_MAP:
        if kw in title:
            return subj
    return '综合'

def parse_version(title):
    m = re.search(r'[（(]([^）)]+)[）)]', title)
    candidates = [m.group(1)] if m else []
    candidates.append(title)
    for text in candidates:
        for kw, ver in VERSION_MAP:
            if kw in text:
                return ver
    return '通用版'

def parse_year(title):
    m = re.search(r'(20\d\d)', title)
    return m.group(1) if m else '未知年份'

def extract_share_id(url):
    m = re.search(r'pan\.quark\.cn/s/([a-zA-Z0-9]+)', url)
    return m.group(1) if m else None

def load_links():
    wb = openpyxl.load_workbook(EXCEL_PATH)
    seen_urls, items = set(), []
    for sheet_name in wb.sheetnames:
        if sheet_name in SKIP_SHEETS:
            continue
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                if not (cell.hyperlink and cell.hyperlink.target and 'quark.cn' in cell.hyperlink.target):
                    continue
                title = str(cell.value or '').strip()
                url = cell.hyperlink.target
                if not title or title in ('夸克链接', '迅雷链接', '百度链接'):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                share_id = extract_share_id(url)
                if not share_id:
                    continue
                items.append({
                    'publisher': sheet_name,
                    'subject': parse_subject(title),
                    'version': parse_version(title),
                    'year': parse_year(title),
                    'title': title,
                    'share_id': share_id,
                    'url': url,
                })
    return items

# ============================
# API
# ============================
def api(method, url, data=None, retries=3):
    body = json.dumps(data).encode() if data is not None else b''
    for attempt in range(retries):
        r = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(r, timeout=20, context=ctx) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {'error': e.code, 'body': e.read().decode()[:200]}
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"    [网络错误] {e.reason} 重试 {attempt+1}/{retries-1}，等待 {wait}s...")
                time.sleep(wait)
            else:
                return {'error': 'URLError', 'body': str(e.reason)}

def mkdir(name, parent_fid):
    res = api('POST', f'{TOKEN_HOST}/1/clouddrive/file?pr=ucpro&fr=pc',
              {"pdir_fid": parent_fid, "file_name": name, "dir_path": "", "dir_init_lock": False})
    if res.get('code') == 0:
        return res['data']['fid']
    # 如果已存在则搜索
    return None

def list_dir(parent_fid):
    res = api('GET', f'{TOKEN_HOST}/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid={parent_fid}&_page=1&_size=100&_fetch_total=1&_sort=file_type:asc,updated_at:desc')
    if res.get('code') == 0:
        return {f['file_name']: f['fid'] for f in res.get('data', {}).get('list', []) if f.get('dir')}
    return {}

def ensure_folder(name, parent_fid, cache):
    key = f'{parent_fid}/{name}'
    if key in cache:
        return cache[key]
    # 先查已有文件夹
    existing = list_dir(parent_fid)
    if name in existing:
        cache[key] = existing[name]
        return existing[name]
    # 不存在则创建
    fid = mkdir(name, parent_fid)
    if fid:
        cache[key] = fid
        return fid
    return None

def get_stoken(share_id):
    res = api('POST',
        f'{TOKEN_HOST}/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc&uc_param_str=&pwd_id={share_id}&passcode=',
        {"pwd_id": share_id, "passcode": ""})
    if res.get('code') == 0:
        return res['data']['stoken']
    return None

def save_share(share_id, stoken, target_fid):
    res = api('POST',
        f'{SAVE_HOST}/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc&uc_param_str=',
        {"pwd_id": share_id, "stoken": stoken, "pdir_fid": "0",
         "to_pdir_fid": target_fid, "pdir_save_all": True, "scene": "link"})
    return res

# ============================
# 主流程
# ============================
def load_done_ids():
    try:
        with open(PROGRESS_FILE, 'r') as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_done_ids(done_ids):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(list(done_ids), f)

def main():
    print("=== 读取 Excel 链接 ===")
    items = load_links()
    print(f"共 {len(items)} 条唯一链接")

    # 断点续传：加载已完成的 share_id
    done_ids = load_done_ids()
    if done_ids:
        print(f"已完成 {len(done_ids)} 条，跳过续传")

    # 加载已有日志（合并结果）
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception:
        results = []

    print("\n=== 建立根文件夹 ===")
    folder_cache = {}
    if DRY_RUN:
        print("[DRY RUN] 跳过实际 API 调用")
        root_fid = 'DRY_ROOT'
    else:
        root_children = list_dir('0')
        if ROOT_NAME in root_children:
            root_fid = root_children[ROOT_NAME]
            print(f"根文件夹已存在: {ROOT_NAME} ({root_fid})")
        else:
            root_fid = mkdir(ROOT_NAME, '0')
            print(f"创建根文件夹: {ROOT_NAME} ({root_fid})")
        folder_cache[f'0/{ROOT_NAME}'] = root_fid

    ok = sum(1 for r in results if r.get('status') == 'ok')
    fail = sum(1 for r in results if r.get('status', '').startswith('fail'))
    skip = len(done_ids)

    print(f"\n=== 开始批量转存（共 {len(items)} 条）===")
    for i, item in enumerate(items, 1):
        subj    = item['subject']
        pub     = item['publisher']
        ver     = item['version']
        year    = item['year']
        share_id = item['share_id']
        title   = item['title']

        folder_path = f"{ROOT_NAME}/{subj}/{pub}/{ver}/{year}"

        # 断点续传：已处理跳过
        if share_id in done_ids:
            print(f"[{i:3d}] ↩ 已完成跳过: {share_id}")
            continue

        if DRY_RUN:
            print(f"[{i:3d}] DRY → {folder_path}\n      {title}")
            results.append({'status': 'dry', **item, 'folder': folder_path})
            continue

        # 确保目录存在
        fid = root_fid
        for part in [subj, pub, ver, year]:
            fid = ensure_folder(part, fid, folder_cache)
            if not fid:
                print(f"[{i:3d}] ✗ 建文件夹失败: {part}")
                break
        if not fid:
            fail += 1
            results.append({'status': 'fail_mkdir', **item})
            continue

        # 获取 stoken 并转存
        stoken = get_stoken(share_id)
        if not stoken:
            print(f"[{i:3d}] ✗ 获取 stoken 失败: {share_id}")
            fail += 1
            results.append({'status': 'fail_token', **item})
            done_ids.add(share_id)
            save_done_ids(done_ids)
            time.sleep(DELAY)
            continue

        res = save_share(share_id, stoken, fid)
        if res.get('code') == 0:
            task_id = res.get('data', {}).get('task_id', '')
            print(f"[{i:3d}] ✓ {subj}/{pub}/{ver}/{year}  task={task_id[:16]}")
            ok += 1
            results.append({'status': 'ok', 'task_id': task_id, **item, 'folder': folder_path})
        else:
            print(f"[{i:3d}] ✗ 转存失败 {share_id}: {res.get('body','')[:80] or res.get('message','')}")
            fail += 1
            results.append({'status': 'fail_save', 'error': str(res), **item})

        done_ids.add(share_id)
        save_done_ids(done_ids)

        # 每10条保存一次日志
        if i % 10 == 0:
            with open(LOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(DELAY)

    # 保存结果日志
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完成 ===")
    print(f"成功: {ok}  失败: {fail}  跳过: {skip}")
    print(f"日志: {LOG_PATH}")

if __name__ == '__main__':
    main()
