# Beijing Paper Scout

Node-based MVP for discovering Beijing middle-school exam-paper metadata from first-tier public sources:

- 课外100
- 鲸题优
- 21世纪教育网
- 教习网

The script indexes public page titles and links only. It does not bypass login, membership, payment, CAPTCHA, CDN challenges, or download restrictions.

## Run

```bash
npm run scrape:papers
```

Useful options:

```bash
npm run scrape:papers -- --output ./data/paper-scout-results.json
npm run scrape:papers -- --max-pages 8 --delay-ms 200
npm run scrape:papers -- --search --keyword "北京 初三 一模 数学 试卷 答案"
```

## Output

Default output:

```text
app/data/paper-scout-results.json
```

Each result contains:

- source id/name
- title
- URL
- discovered-from URL
- discovery kind
- districts
- subjects
- exam types
- grades
- years
- relevance score

## Next steps

- Store results in SQLite/PostgreSQL and diff by normalized URL.
- Add a scheduled job for daily/hourly monitoring.
- Add per-site adapters when a source needs custom parsing.
- Add manual-review workflow for pages that require login or human verification.
