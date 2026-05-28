#!/usr/bin/env python3
"""
北京高中中考录取分数线爬取脚本
从 gaokzx.com 抓取 2024+2025 各区分数线
"""

import re
import json
import time
import subprocess
from pathlib import Path
from html.parser import HTMLParser

BASE_DIR = Path('/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-highschools')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'

# District mapping: abbrev -> full name
DISTRICT_MAP = {
    '海淀': '海淀区', '东城': '东城区', '西城': '西城区', '朝阳': '朝阳区',
    '丰台': '丰台区', '石景山': '石景山区', '房山': '房山区', '通州': '通州区',
    '顺义': '顺义区', '昌平': '昌平区', '大兴': '大兴区', '怀柔': '怀柔区',
    '门头沟': '门头沟区', '平谷': '平谷区', '密云': '密云区', '延庆': '延庆区',
    '经开': '北京经济技术开发区', '燕山': '燕山地区',
}

# 2025 district pages (from 144703 article)
PAGES_2025 = {
    '海淀': 'https://www.gaokzx.com/gk/zhongkao/144855.html',
    '东城': 'https://www.gaokzx.com/gk/zhongkao/144856.html',
    '西城': 'https://www.gaokzx.com/gk/zhongkao/144857.html',
    '朝阳': 'https://www.gaokzx.com/gk/zhongkao/144858.html',
    '丰台': 'https://www.gaokzx.com/gk/zhongkao/144859.html',
    '石景山': 'https://www.gaokzx.com/gk/zhongkao/144973.html',
    '房山': 'https://www.gaokzx.com/gk/zhongkao/144972.html',
    '通州': 'https://www.gaokzx.com/gk/zhongkao/144865.html',
    '顺义': 'https://www.gaokzx.com/gk/zhongkao/144861.html',
    # 昌平 2025: 144860 is wrong page (about 玉泉school). Need correct ID.
    # '昌平': 'https://www.gaokzx.com/gk/zhongkao/XXXX.html',
    '大兴': 'https://www.gaokzx.com/gk/zhongkao/144863.html',
    '经开': 'https://www.gaokzx.com/gk/zhongkao/144862.html',
}

# 2024 district pages (verified by title check)
PAGES_2024 = {
    '海淀': 'https://www.gaokzx.com/gk/zhongkao/126160.html',
    '东城': 'https://www.gaokzx.com/gk/zhongkao/126164.html',
    '西城': 'https://www.gaokzx.com/gk/zhongkao/126162.html',
    '朝阳': 'https://www.gaokzx.com/gk/zhongkao/126165.html',
    '丰台': 'https://www.gaokzx.com/gk/zhongkao/126166.html',
    '石景山': 'https://www.gaokzx.com/gk/zhongkao/126167.html',
    '通州': 'https://www.gaokzx.com/gk/zhongkao/126163.html',   # was wrong as 房山
    '昌平': 'https://www.gaokzx.com/gk/zhongkao/126168.html',   # was wrong as 顺义
    '大兴': 'https://www.gaokzx.com/gk/zhongkao/126169.html',
    '延庆': 'https://www.gaokzx.com/gk/zhongkao/126231.html',   # was wrong as 怀柔
    '经开': 'https://www.gaokzx.com/gk/zhongkao/126230.html',
    # 128492 is 2023年平谷, skip
}


def fetch_html(url: str) -> str:
    result = subprocess.run(
        ['curl', '-s', '-L', '--max-time', '20',
         '-H', f'User-Agent: {UA}', url],
        capture_output=True, text=True
    )
    return result.stdout


def extract_content(html: str):
    """Extract article HTML content from Nuxt SSR JSON"""
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    if len(scripts) < 6:
        return None
    s = scripts[5]
    try:
        data = json.loads(s)
    except Exception:
        return None
    # Find the string item that contains a <table
    for item in data:
        if isinstance(item, str) and '<table' in item and len(item) > 500:
            return item
    # Fallback: find any long string with score pattern
    for item in data:
        if isinstance(item, str) and len(item) > 300 and ('分数' in item or '录取' in item):
            return item
    return None


class TableParser(HTMLParser):
    """Parse HTML tables into list of rows"""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = ''
        self.in_cell = False
        self.in_table = False
        self.rowspan_queue = {}  # col_idx -> (remaining, text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            self.in_table = True
            self.current_table = []
            self.rowspan_queue = {}
        elif tag == 'tr':
            self.current_row = []
            self.col_idx = 0
        elif tag in ('td', 'th'):
            # Handle rowspan
            rowspan = int(attrs.get('rowspan', 1))
            colspan = int(attrs.get('colspan', 1))
            self.current_cell = ''
            self.in_cell = True
            self._current_rowspan = rowspan
            self._current_colspan = colspan
        elif tag == 'br' and self.in_cell:
            self.current_cell += ' '

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.in_cell:
            text = re.sub(r'\s+', ' ', self.current_cell).strip()
            # handle pending rowspans at this col position
            while self.col_idx in self.rowspan_queue and self.rowspan_queue[self.col_idx][0] > 0:
                rs_text = self.rowspan_queue[self.col_idx][1]
                self.current_row.append(rs_text)
                remaining = self.rowspan_queue[self.col_idx][0] - 1
                if remaining == 0:
                    del self.rowspan_queue[self.col_idx]
                else:
                    self.rowspan_queue[self.col_idx] = (remaining, rs_text)
                self.col_idx += 1
            # Add this cell (repeated for colspan)
            for _ in range(self._current_colspan):
                self.current_row.append(text)
            # Register rowspan
            if self._current_rowspan > 1:
                for ci in range(self.col_idx, self.col_idx + self._current_colspan):
                    self.rowspan_queue[ci] = (self._current_rowspan - 1, text)
            self.col_idx += self._current_colspan
            self.in_cell = False
        elif tag == 'tr':
            # flush remaining rowspans
            while self.col_idx in self.rowspan_queue and self.rowspan_queue[self.col_idx][0] > 0:
                rs_text = self.rowspan_queue[self.col_idx][1]
                self.current_row.append(rs_text)
                remaining = self.rowspan_queue[self.col_idx][0] - 1
                if remaining == 0:
                    del self.rowspan_queue[self.col_idx]
                else:
                    self.rowspan_queue[self.col_idx] = (remaining, rs_text)
                self.col_idx += 1
            if self.current_row:
                self.current_table.append(self.current_row)
        elif tag == 'table':
            if self.current_table:
                self.tables.append(self.current_table)
            self.in_table = False

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


def parse_score(text: str):
    """Extract numeric score from text like '487', '646分', '646', etc."""
    text = re.sub(r'[^\d]', '', text.strip())
    if text and text.isdigit():
        v = int(text)
        # Sanity check: 中考分数应在200-750之间
        if 200 <= v <= 750:
            return v
    return None


def parse_rank(text: str):
    """Extract numeric rank"""
    text = re.sub(r'[^\d]', '', text.strip())
    if text and text.isdigit():
        return int(text)
    return None


def is_header_row(row: list) -> bool:
    """Check if a row is a column-label header (not a data row)"""
    text = ' '.join(row)
    if not any(k in text for k in ['学校', '名称', '序号', '排名', '录取分数', '专业']):
        return False
    # Real header rows don't contain actual score numbers (200-750)
    for cell in row:
        v = parse_score(cell)
        if v is not None:
            return False  # Has a score value → it's a data row, not header
    return True


def is_title_row(row: list) -> bool:
    """Check if a row is a table title (large colspan cell with description)"""
    # A true title row has ALL cells the same value (pure colspan expansion)
    if len(set(row)) == 1 and len(row) > 2:
        text = row[0]
        return len(text) > 5 and any(k in text for k in ['分数线', '录取', '招生', '排名'])
    return False


def extract_scores_from_content(content: str, district: str, year: int) -> list:
    """Parse score table from article HTML content"""
    parser = TableParser()
    parser.feed(content)

    results = []

    for table in parser.tables:
        if len(table) < 3:
            continue

        # Skip navigation/index tables (only link text, no scores)
        all_text = ' '.join(' '.join(r) for r in table)
        if '<' in all_text:  # still has HTML - shouldn't happen but skip
            continue

        # Find real column header row (has '学校', '名称' etc.)
        # Skip title rows (large colspan cells) and find the real header
        header_row = None
        data_start = 0

        for i, row in enumerate(table):
            if is_title_row(row):
                continue  # skip title rows
            if is_header_row(row):
                header_row = row
                data_start = i + 1
                break

        # If still not found, skip first 1-2 rows heuristically
        if header_row is None:
            for start_i in range(min(3, len(table))):
                test_row = table[start_i]
                test_text = ' '.join(test_row)
                if '学校' in test_text or '名称' in test_text:
                    header_row = test_row
                    data_start = start_i + 1
                    break
            if header_row is None:
                data_start = min(2, len(table) - 1)

        # Detect column indices from header
        school_col = None
        score_col = None
        rank_col = None

        if header_row:
            # De-duplicate header cells (merged colspan cells appear multiple times)
            seen_header_cells = set()
            unique_header = []
            for ci, cell in enumerate(header_row):
                if cell not in seen_header_cells:
                    seen_header_cells.add(cell)
                    unique_header.append((ci, cell))

            for ci, cell in unique_header:
                # '专业名称' contains '名称' but is NOT the school column
                if school_col is None and ('学校' in cell or cell.strip() in ('名称', '校名')):
                    school_col = ci
                elif score_col is None and ('分数' in cell or '录取' in cell):
                    score_col = ci
                elif rank_col is None and '排名' in cell:
                    rank_col = ci
                elif '序号' in cell or cell.strip() in ('序', '编号'):
                    pass  # skip serial number column

        # If school_col not found from header, detect from data rows
        # by finding the first column with real school names (Chinese >=4 chars, not score text)
        if school_col is None:
            for test_row in table[data_start:data_start+8]:
                for ci, cell in enumerate(test_row):
                    cell = cell.strip()
                    # A school name has Chinese characters, length >=4, doesn't look like score
                    if (len(cell) >= 4 and re.search(r'[一-鿿]{3,}', cell)
                            and not re.match(r'^\d+分?$', cell)
                            and '分数' not in cell and '排名' not in cell
                            and '录取' not in cell):
                        school_col = ci
                        break
                if school_col is not None:
                    break

        if school_col is None:
            continue

        # Find score column: column with numbers in valid score range (200-750)
        if score_col is None:
            for test_row in table[data_start:data_start+10]:
                for ci, cell in enumerate(test_row):
                    if ci == school_col:
                        continue
                    v = parse_score(cell)
                    if v is not None:
                        score_col = ci
                        break
                if score_col is not None:
                    break

        # Find rank column: column with numbers > 100 (district ranks)
        if rank_col is None and score_col is not None:
            for test_row in table[data_start:data_start+10]:
                for ci, cell in enumerate(test_row):
                    if ci in (school_col, score_col):
                        continue
                    v = parse_rank(cell)
                    if v is not None and v > 100:
                        rank_col = ci
                        break
                if rank_col is not None:
                    break

        # Parse data rows
        current_school = None
        for row in table[data_start:]:
            # Skip note rows, header repeats, etc.
            if len(row) <= 1:
                continue
            row_text = ' '.join(row)
            if '注意' in row_text or '说明' in row_text or '网传' in row_text or '分数线' in row_text[:5]:
                continue
            # Skip if row_text looks like a section header
            if len(row_text) < 3:
                continue

            # Get school name
            if school_col < len(row):
                cell = row[school_col].strip()
                if cell and re.search(r'[一-鿿]{2,}', cell) and not re.match(r'^\d+分?$', cell):
                    # Looks like a school/program name with Chinese chars
                    current_school = cell
                elif cell == '' and current_school:
                    # Continuation row (rowspan)
                    pass
                # else: pure number or empty - keep previous school name

            if not current_school:
                continue

            # Get program/class name (may be another column)
            program = None
            # Look for program info embedded in school name or separate column
            # Some tables have: school | program | score | rank
            # Others have: school | score | rank

            # Get score
            score = None
            if score_col is not None and score_col < len(row):
                # The score column might have "school+score" or just score
                cell = row[score_col].strip()
                # Extract score even if mixed with text
                score = parse_score(cell)
                if score is None:
                    # Try looking in other columns
                    for ci, c in enumerate(row):
                        if ci == school_col:
                            continue
                        s = parse_score(c)
                        if s is not None:
                            score = s
                            break
            else:
                for ci, c in enumerate(row):
                    if ci == school_col:
                        continue
                    s = parse_score(c)
                    if s is not None:
                        score = s
                        break

            if score is None:
                continue

            # Get rank
            rank = None
            if rank_col is not None and rank_col < len(row):
                rank = parse_rank(row[rank_col])

            # Normalize school name
            school = re.sub(r'[·\s]+', '', current_school).strip()

            results.append({
                'district': DISTRICT_MAP.get(district, district + '区'),
                'school': school,
                'year': year,
                'score': score,
                'district_rank': rank,
            })

    return results


def scrape_year(year: int, pages: dict) -> list[dict]:
    all_results = []
    for district, url in pages.items():
        print(f'  Fetching {year} {district} ... {url}')
        html = fetch_html(url)
        if not html:
            print(f'    FAILED: empty response')
            continue
        content = extract_content(html)
        if not content:
            print(f'    FAILED: no content extracted')
            continue
        records = extract_scores_from_content(content, district, year)
        print(f'    Got {len(records)} score records')
        all_results.extend(records)
        time.sleep(0.5)  # polite delay
    return all_results


def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    all_scores = []

    print('=== Scraping 2025 scores ===')
    scores_2025 = scrape_year(2025, PAGES_2025)
    all_scores.extend(scores_2025)

    print('\n=== Scraping 2024 scores ===')
    scores_2024 = scrape_year(2024, PAGES_2024)
    all_scores.extend(scores_2024)

    # Save raw scores
    out_path = BASE_DIR / 'scores_raw.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_scores, f, ensure_ascii=False, indent=2)
    print(f'\nSaved {len(all_scores)} total records to {out_path}')

    # Print summary
    by_year_district = {}
    for r in all_scores:
        key = (r['year'], r['district'])
        by_year_district.setdefault(key, []).append(r)

    print('\nSummary:')
    for key in sorted(by_year_district.keys()):
        y, d = key
        print(f'  {y} {d}: {len(by_year_district[key])} records')


if __name__ == '__main__':
    main()
