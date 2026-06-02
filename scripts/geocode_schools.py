#!/usr/bin/env python3
"""
通过 OpenStreetMap Nominatim 批量查询北京高中地址
Nominatim 免费，无需 API Key，限速 1 req/s
"""
import json
import time
import urllib.parse
import subprocess
from pathlib import Path

BASE_DIR = Path('/Users/jiakui/projects/zhongkao-agent/knowledge-original/beijing-highschools')
UA = 'ZhongkaoAgent/1.0 (educational research)'
DELAY = 1.2  # seconds between requests


def nominatim_search(query: str) -> list:
    url = (
        f'https://nominatim.openstreetmap.org/search'
        f'?q={urllib.parse.quote(query)}'
        f'&format=json&limit=5&countrycodes=cn'
        f'&addressdetails=1'
    )
    result = subprocess.run(
        ['curl', '-s', '--max-time', '10', '-H', f'User-Agent: {UA}', url],
        capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        return []


def find_best_match(results: list, district: str, school_name: str):
    """Find the best geocoding result for a school in the given district"""
    # Prefer results that mention the district
    for r in results:
        display = r.get('display_name', '')
        if district in display:
            return r
    # Fallback: first result in Beijing
    for r in results:
        display = r.get('display_name', '')
        if '北京' in display:
            return r
    return results[0] if results else None


def format_address(result: dict) -> str:
    """Format address from Nominatim result"""
    addr = result.get('address', {})
    parts = []
    for key in ['road', 'suburb', 'town', 'city_district', 'county', 'city', 'postcode']:
        v = addr.get(key)
        if v and v not in parts:
            parts.append(v)
    return ', '.join(parts) if parts else result.get('display_name', '')[:80]


def main():
    # Load school list
    with open(BASE_DIR / 'schools_2026.json', encoding='utf-8') as f:
        data = json.load(f)
    schools = data.get('schools', data) if isinstance(data, dict) else data

    # Load existing geocoding cache if any
    cache_path = BASE_DIR / 'geocode_cache.json'
    cache = {}
    if cache_path.exists():
        with open(cache_path, encoding='utf-8') as f:
            cache = json.load(f)
        print(f'Loaded {len(cache)} cached results')

    results = []
    total = len(schools)

    for i, school in enumerate(schools):
        name = school['name']
        district = school['district']
        key = f'{district}_{name}'

        if key in cache:
            results.append(cache[key])
            continue

        print(f'[{i+1}/{total}] {district} {name}...')

        # Try full name first, then with district
        geo_result = None

        # Query 1: full official name + district
        q1 = f'{name} {district} 北京'
        r1 = nominatim_search(q1)
        time.sleep(DELAY)

        match = find_best_match(r1, district, name)

        if not match:
            # Query 2: simplified name (remove '北京市' prefix)
            simplified = name.replace('北京市', '').replace('北京', '').strip()
            if simplified != name:
                q2 = f'{simplified} {district} 北京'
                r2 = nominatim_search(q2)
                time.sleep(DELAY)
                match = find_best_match(r2, district, simplified)

        if match:
            geo_result = {
                'district': district,
                'name': name,
                'lat': float(match['lat']),
                'lon': float(match['lon']),
                'address': format_address(match),
                'display_name': match.get('display_name', '')[:120],
                'osm_type': match.get('osm_type', ''),
                'osm_id': match.get('osm_id', ''),
            }
        else:
            geo_result = {
                'district': district,
                'name': name,
                'lat': None,
                'lon': None,
                'address': None,
                'note': 'not_found',
            }
            print(f'  NOT FOUND')

        cache[key] = geo_result
        results.append(geo_result)

        # Save cache every 20 requests
        if (i + 1) % 20 == 0:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            print(f'  Cache saved ({len(cache)} entries)')

    # Final save
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    out_path = BASE_DIR / 'school_addresses.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    found = sum(1 for r in results if r.get('lat'))
    print(f'\nDone: {found}/{total} found ({found/total*100:.1f}%)')
    print(f'Saved to {out_path}')


if __name__ == '__main__':
    main()
