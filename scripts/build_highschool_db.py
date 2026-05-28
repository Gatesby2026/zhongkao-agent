#!/usr/bin/env python3
"""
合并高中名单 + 分数线 → 最终数据库
"""
import re
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path('/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-highschools')


def clean_school_name(name: str) -> str:
    """Remove embedded scores from school names like '北京四中487' → '北京四中'"""
    # Remove trailing numbers (scores) that got merged into name
    name = re.sub(r'\s*\d{3}\s*$', '', name).strip()
    # Remove 分/班 qualifiers from programs mixed into school names
    # e.g. '科技综合素质实验班 484' - already handled by trailing number removal
    return name.strip()


def normalize_school_name(name: str) -> str:
    """Normalize school name for matching purposes"""
    name = clean_school_name(name)
    # Remove whitespace
    name = re.sub(r'\s+', '', name)
    # Normalize common abbreviations
    replacements = {
        '北京市': '',
        '北京': '',
        '学校': '',
        '中学': '中',
        '附属中学': '附中',
        '第': '',
        '实验中学': '实验',
    }
    # Don't over-normalize - just strip and return clean
    return name


def load_schools():
    """Load the 2025 school list"""
    with open(BASE_DIR / 'schools_2025.json', encoding='utf-8') as f:
        data = json.load(f)
    # Handle both list and dict with 'schools' key
    if isinstance(data, dict):
        return data.get('schools', [])
    return data


def load_scores():
    """Load raw scores and clean them"""
    with open(BASE_DIR / 'scores_raw.json', encoding='utf-8') as f:
        raw = json.load(f)

    cleaned = []
    for r in raw:
        school = clean_school_name(r['school'])
        if not school or len(school) < 2:
            continue
        # Skip obvious non-school entries
        if re.match(r'^\d+分?$', school):
            continue
        cleaned.append({
            'district': r['district'],
            'school': school,
            'year': r['year'],
            'score': r['score'],
            'district_rank': r['district_rank'],
        })
    return cleaned


def build_score_index(scores: list) -> dict:
    """Build index: (district, school_clean) → {year: [(score, rank), ...]}"""
    index = defaultdict(lambda: defaultdict(list))
    for r in scores:
        key = (r['district'], r['school'])
        index[key][r['year']].append({
            'score': r['score'],
            'rank': r['district_rank'],
        })
    return dict(index)


def get_best_score(entries: list) -> dict:
    """Get the lowest (best, most selective) score among program entries for a year"""
    if not entries:
        return None
    # Use the min score as the school's "floor" admission score
    # Use the max score as the "most selective program" score
    scores = [e['score'] for e in entries if e['score']]
    ranks = [e['rank'] for e in entries if e['rank']]
    if not scores:
        return None
    return {
        'min_score': min(scores),   # least selective program
        'max_score': max(scores),   # most selective program
        'rank_at_min': max(ranks) if ranks else None,  # rank corresponding to min score
        'rank_at_max': min(ranks) if ranks else None,  # rank corresponding to max score
    }


def load_name_mapping():
    """Load school name mapping from score names to official names"""
    mapping_path = BASE_DIR / 'score_name_mapping.json'
    if not mapping_path.exists():
        return {}
    with open(mapping_path, encoding='utf-8') as f:
        raw = json.load(f)
    # Convert to (district, score_name) → (official_district, official_name)
    result = {}
    for key, val in raw.items():
        dist, name = key.split('|', 1)
        result[(dist, name)] = (val['matched_district'], val['matched_name'])
    return result


def main():
    schools = load_schools()
    scores = load_scores()
    name_mapping = load_name_mapping()

    print(f'Schools in list: {len(schools)}')
    print(f'Score records: {len(scores)}')
    print(f'Name mappings loaded: {len(name_mapping)}')

    # Build per-school score data, normalizing school names via mapping
    score_by_official_name = defaultdict(lambda: defaultdict(list))
    for r in scores:
        score_school = r['school']
        score_district = r['district']

        # Try to map to official name
        key = (score_district, score_school)
        if key in name_mapping:
            off_district, off_name = name_mapping[key]
        else:
            # Use as-is
            off_district, off_name = score_district, score_school

        score_by_official_name[(off_district, off_name)][r['year']].append({
            'score': r['score'],
            'rank': r['district_rank'],
        })

    # Build final school database
    db = []
    matched_official = set()

    for school_info in schools:
        district = school_info['district']
        name = school_info['name']

        school_record = {
            'name': name,
            'district': district,
            'scores': {},
        }

        # Look up scores
        key = (district, name)
        if key in score_by_official_name:
            matched_official.add(key)
            for year_key in [2025, 2024]:
                if year_key in score_by_official_name[key]:
                    best = get_best_score(score_by_official_name[key][year_key])
                    if best:
                        school_record['scores'][str(year_key)] = best

        db.append(school_record)

    # Also include schools with scores not matched to official list
    listed_keys = {(s['district'], s['name']) for s in schools}
    for (dist, name), year_data in score_by_official_name.items():
        if (dist, name) in listed_keys or (dist, name) in matched_official:
            continue
        school_record = {
            'name': name,
            'district': dist,
            'scores': {},
            'note': 'not_in_2025_official_list',
        }
        for year_key in [2025, 2024]:
            if year_key in year_data:
                best = get_best_score(year_data[year_key])
                if best:
                    school_record['scores'][str(year_key)] = best
        db.append(school_record)

    # Sort by district then name
    db.sort(key=lambda x: (x['district'], x['name']))

    # Summary
    schools_with_2025 = sum(1 for s in db if '2025' in s.get('scores', {}))
    schools_with_2024 = sum(1 for s in db if '2024' in s.get('scores', {}))
    schools_with_any = sum(1 for s in db if s.get('scores'))
    print(f'\nDatabase: {len(db)} schools total')
    print(f'  With 2025 scores: {schools_with_2025}')
    print(f'  With 2024 scores: {schools_with_2024}')
    print(f'  With any scores: {schools_with_any}')
    print(f'  No scores: {len(db) - schools_with_any}')

    # Save
    out_path = BASE_DIR / 'schools_db.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f'\nSaved to {out_path}')

    # Print sample
    print('\nSample (first 10 with scores):')
    shown = 0
    for s in db:
        if s.get('scores') and shown < 10:
            score_str = ', '.join(
                f"{y}:{v['max_score']}/{v['min_score']}"
                for y, v in sorted(s['scores'].items(), reverse=True)
            )
            print(f'  [{s["district"]}] {s["name"]}: {score_str}')
            shown += 1

    # Score stats
    print('\nScore range by district (2025):')
    dist_scores = defaultdict(list)
    for r in scores:
        if r['year'] == 2025:
            dist_scores[r['district']].append(r['score'])
    for dist in sorted(dist_scores):
        sc = dist_scores[dist]
        print(f'  {dist}: {min(sc)}-{max(sc)} ({len(sc)} programs)')


if __name__ == '__main__':
    main()
