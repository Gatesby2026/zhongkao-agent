#!/usr/bin/env python3
"""
匹配分数线中的学校名称 → 官方名单中的标准名称
使用字符级别相似度 + 规则化处理
"""
import re
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path('/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-highschools')

# Common abbreviations in score data vs full names in official list
ABBREV_MAP = {
    '二中': '第二中学',
    '五中': '第五中学',
    '四中': '第四中学',
    '八中': '第八中学',
    '三中': '第三中学',
    '六中': '第六中学',
    '七中': '第七中学',
    '一中': '第一中学',
    '九中': '第九中学',
    '十中': '第十中学',
    '十一中': '第十一中学',
    '十二中': '第十二中学',
    '十三中': '第十三中学',
    '十四中': '第十四中学',
    '十五中': '第十五中学',
    '十六中': '第十六中学',
    '十七中': '第十七中学',
    '十八中': '第十八中学',
    '二十中': '第二十中学',
    '二十二中': '第二十二中学',
    '二十四中': '第二十四中学',
    '二十五中': '第二十五中学',
    '二十七中': '第二十七中学',
    '三十一中': '第三十一中学',
    '三十五中': '第三十五中学',
    '三十九中': '第三十九中学',
    '四十三中': '第四十三中学',
    '四十四中': '第四十四中学',
    '五十中': '第五十中学',
    '五十五中': '第五十五中学',
    '五十六中': '第五十六中学',
    '六十六中': '第六十六中学',
    '八十中': '第八十中学',
    '一零九中': '第一〇九中学',
    '一六六中': '第一六六中学',
    '一六一中': '第一六一中学',
    '171中': '第一七一中学',
    '八十中': '第八十中学',
}


def normalize(name: str) -> str:
    """Normalize school name for comparison"""
    # Remove whitespace
    name = re.sub(r'\s+', '', name)
    # Remove common prefixes
    for prefix in ['北京市', '北京']:
        name = name.replace(prefix, '', 1)
    # Normalize number words
    name = name.replace('第一〇九', '一零九')
    name = name.replace('第一七一', '171')
    name = name.replace('第一六六', '一六六')
    name = name.replace('第一六一', '一六一')
    name = name.replace('第八十', '八十')
    # Remove trailing qualifiers
    name = name.replace('学校', '').replace('（本部）', '').replace('(本部)', '')
    # Remove 中学 vs 中 inconsistency
    # Keep as is for now
    return name.strip()


def char_similarity(a: str, b: str) -> float:
    """Character-level similarity between two strings"""
    if not a or not b:
        return 0.0
    a_set = set(a)
    b_set = set(b)
    intersection = len(a_set & b_set)
    union = len(a_set | b_set)
    jaccard = intersection / union if union > 0 else 0.0

    # Also check if one is substring of other
    if a in b or b in a:
        return max(0.8, jaccard)

    return jaccard


def find_best_match(score_name: str, official_names: list, district: str) -> tuple:
    """Find best matching official school name for a score data school name"""
    norm_score = normalize(score_name)

    best_name = None
    best_score = 0.0

    # Filter by district first
    district_schools = [n for n in official_names if n[0] == district]
    if not district_schools:
        district_schools = official_names  # fallback to all

    for off_district, off_name in district_schools:
        norm_off = normalize(off_name)

        sim = char_similarity(norm_score, norm_off)

        # Boost for exact normalized match
        if norm_score == norm_off:
            sim = 1.0
        # Boost for substring
        elif norm_score in norm_off or norm_off in norm_score:
            sim = max(sim, 0.85)

        if sim > best_score:
            best_score = sim
            best_name = (off_district, off_name)

    return best_name, best_score


def main():
    # Load data
    with open(BASE_DIR / 'schools_2025.json', encoding='utf-8') as f:
        data = json.load(f)
    schools_list = data.get('schools', data) if isinstance(data, dict) else data
    official_names = [(s['district'], s['name']) for s in schools_list]

    with open(BASE_DIR / 'scores_raw.json', encoding='utf-8') as f:
        scores = json.load(f)

    # Get unique (district, school) pairs from scores
    score_schools = set()
    for r in scores:
        score_schools.add((r['district'], r['school']))

    print(f'Official schools: {len(official_names)}')
    print(f'Score schools (unique): {len(score_schools)}')

    # Build mapping
    mapping = {}  # score_school → official_school
    unmatched = []

    for dist, name in sorted(score_schools):
        best, score = find_best_match(name, official_names, dist)
        if best and score >= 0.5:
            mapping[(dist, name)] = (best[0], best[1], score)
        else:
            unmatched.append((dist, name, best, score))

    print(f'\nMapped: {len(mapping)}/{len(score_schools)}')

    # Show mappings with low confidence
    print('\nLow confidence mappings (0.5-0.7):')
    for (dist, name), (off_dist, off_name, conf) in sorted(mapping.items(), key=lambda x: x[1][2]):
        if conf < 0.7:
            print(f'  {dist} {name!r} → {off_name!r} (conf={conf:.2f})')

    print('\nUnmatched (similarity < 0.5):')
    for dist, name, best, score in unmatched[:20]:
        print(f'  {dist} {name!r} → best={best} (sim={score:.2f})')

    # Save mapping
    mapping_out = {}
    for (dist, name), (off_dist, off_name, conf) in mapping.items():
        mapping_out[f'{dist}|{name}'] = {
            'matched_district': off_dist,
            'matched_name': off_name,
            'confidence': conf,
        }

    out_path = BASE_DIR / 'score_name_mapping.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(mapping_out, f, ensure_ascii=False, indent=2)
    print(f'\nSaved mapping to {out_path}')


if __name__ == '__main__':
    main()
