#!/usr/bin/env python3
"""
最终合并：学校列表 + 分数线 + 地址 + 排名 → 完整数据库
"""
import json
import re
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path('/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-highschools')


def load_db():
    with open(BASE_DIR / 'schools_db.json', encoding='utf-8') as f:
        return json.load(f)


def load_addresses():
    addr_path = BASE_DIR / 'school_addresses.json'
    if not addr_path.exists():
        print('Warning: school_addresses.json not found')
        return {}
    with open(addr_path, encoding='utf-8') as f:
        raw = json.load(f)
    result = {}
    for r in raw:
        if r.get('lat'):
            result[(r['district'], r['name'])] = {
                'lat': r['lat'],
                'lon': r['lon'],
                'address': r.get('address', ''),
            }
    return result


def compute_rankings(db: list) -> dict:
    """Compute district rankings by 2025 score"""
    # Group by district, sort by max score descending
    by_district = defaultdict(list)
    for school in db:
        if '2025' in school.get('scores', {}):
            s = school['scores']['2025']
            by_district[school['district']].append({
                'name': school['name'],
                'max_score': s['max_score'],
                'min_score': s['min_score'],
            })

    rankings = {}  # (district, name) → district_rank_2025
    for district, schools in by_district.items():
        # Sort by min_score descending (overall selectivity)
        sorted_schools = sorted(schools, key=lambda x: x['min_score'], reverse=True)
        for rank, school in enumerate(sorted_schools, 1):
            rankings[(district, school['name'])] = rank

    return rankings


def main():
    db = load_db()
    addresses = load_addresses()
    rankings = compute_rankings(db)

    print(f'Schools in DB: {len(db)}')
    print(f'Address records: {len(addresses)}')
    print(f'Schools with 2025 rankings: {len(rankings)}')

    # Build final unified structure
    final = []
    for school in db:
        district = school['district']
        name = school['name']

        record = {
            'district': district,
            'name': name,
        }

        # Add address
        key = (district, name)
        if key in addresses:
            addr = addresses[key]
            record['lat'] = addr['lat']
            record['lon'] = addr['lon']
            record['address'] = addr['address']

        # Add scores
        if school.get('scores'):
            record['scores'] = school['scores']

        # Add computed district ranking (within district, by 2025 score)
        if key in rankings:
            record['district_rank_2025'] = rankings[key]

        # Flag
        if school.get('note'):
            record['note'] = school['note']

        final.append(record)

    # Sort by district, then by 2025 min score desc, then name
    def sort_key(s):
        score = s.get('scores', {}).get('2025', {}).get('min_score', 0) or 0
        return (s['district'], -score, s['name'])

    final.sort(key=sort_key)

    # Save final JSON
    out_path = BASE_DIR / 'highschools_final.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f'Saved {len(final)} records to {out_path}')

    # Summary stats
    has_addr = sum(1 for s in final if s.get('address'))
    has_score = sum(1 for s in final if s.get('scores'))
    has_2025 = sum(1 for s in final if '2025' in s.get('scores', {}))
    has_2024 = sum(1 for s in final if '2024' in s.get('scores', {}))
    print(f'\nData coverage:')
    print(f'  With addresses: {has_addr}/{len(final)} ({has_addr/len(final)*100:.0f}%)')
    print(f'  With any scores: {has_score}/{len(final)} ({has_score/len(final)*100:.0f}%)')
    print(f'  With 2025 scores: {has_2025}/{len(final)}')
    print(f'  With 2024 scores: {has_2024}/{len(final)}')

    # Top 10 per key district
    print('\n=== Top 10 schools by 2025 min admission score ===')
    district_tops = defaultdict(list)
    for s in final:
        if '2025' in s.get('scores', {}):
            sc = s['scores']['2025']
            district_tops[s['district']].append((sc['max_score'], sc['min_score'], s['name']))

    for district in ['西城区', '东城区', '海淀区', '朝阳区']:
        tops = sorted(district_tops.get(district, []), reverse=True)[:5]
        print(f'\n{district}:')
        for max_sc, min_sc, name in tops:
            print(f'  {name}: {max_sc}/{min_sc}分')

    # Citywide top schools by 2025 max score
    print('\n=== 2025 全市 TOP 15 高中（按最高录取分数线排序）===')
    all_schools = []
    for s in final:
        if '2025' in s.get('scores', {}):
            sc = s['scores']['2025']
            all_schools.append((sc['max_score'], sc['min_score'], s['district'], s['name']))
    all_schools.sort(reverse=True)
    for max_sc, min_sc, dist, name in all_schools[:15]:
        print(f'  {dist} {name}: {max_sc}/{min_sc}分')


if __name__ == '__main__':
    main()
