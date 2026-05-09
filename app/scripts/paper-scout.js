#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { setTimeout: delay } = require("node:timers/promises");

const DEFAULT_OUTPUT = path.join(process.cwd(), "data", "paper-scout-results.json");
const USER_AGENT =
  "zhongkao-paper-scout/0.1 (+https://github.com/Gatesby2026; contact: jiakui191@gmail.com)";

const DISTRICTS = [
  "海淀",
  "西城",
  "东城",
  "朝阳",
  "丰台",
  "石景山",
  "通州",
  "昌平",
  "大兴",
  "房山",
  "顺义",
  "门头沟",
  "密云",
  "平谷",
  "怀柔",
  "延庆",
  "燕山",
];

const SUBJECTS = ["语文", "数学", "英语", "物理", "化学", "道德与法治", "道法", "政治", "历史", "地理", "生物"];
const EXAM_TYPES = ["一模", "二模", "期中", "期末", "适应性练习", "综合练习", "中考模拟"];
const GRADES = ["初一", "初二", "初三", "七年级", "八年级", "九年级"];

const DEFAULT_KEYWORDS = [
  "北京 初三 一模 试卷 答案",
  "北京 初三 二模 试卷 答案",
  "北京 九年级 期中 试卷 答案",
  "北京 九年级 期末 试卷 答案",
  "北京 初中 期中 期末 试卷 答案",
];

const SOURCES = [
  {
    id: "kewai100",
    name: "课外100",
    priority: 1,
    urls: [
      "http://kewai100.com/col.jsp?id=170",
      "http://kewai100.cn/nd.jsp?id=1079",
      "http://kewai100.com/nd.jsp?id=1086",
    ],
  },
  {
    id: "jingtiyou",
    name: "鲸题优",
    priority: 1,
    urls: ["https://www.jingtiyou.cn/"],
  },
  {
    id: "21cnjy",
    name: "21世纪教育网",
    priority: 1,
    urls: ["https://zy.21cnjy.com/23069813", "https://mip.21cnjy.com/P/23067808.html"],
    searchTemplates: [
      "https://zy.21cnjy.com/search?keyword={query}",
      "https://zy.21cnjy.com/h?keyword={query}",
    ],
  },
  {
    id: "51jiaoxi",
    name: "教习网",
    priority: 1,
    urls: ["https://www.51jiaoxi.com/album-122065.html", "https://www.51jiaoxi.com/pack-2421.html"],
    searchTemplates: ["https://www.51jiaoxi.com/search.html?keyword={query}"],
  },
];

function parseArgs(argv) {
  const args = {
    output: DEFAULT_OUTPUT,
    keywords: DEFAULT_KEYWORDS,
    maxPages: 40,
    delayMs: 800,
    includeSearch: false,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--output" && next) {
      args.output = path.resolve(next);
      i += 1;
    } else if (arg === "--keyword" && next) {
      args.keywords = [next];
      i += 1;
    } else if (arg === "--keywords" && next) {
      args.keywords = next
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      i += 1;
    } else if (arg === "--max-pages" && next) {
      args.maxPages = Number(next);
      i += 1;
    } else if (arg === "--delay-ms" && next) {
      args.delayMs = Number(next);
      i += 1;
    } else if (arg === "--search") {
      args.includeSearch = true;
    } else if (arg === "--no-search") {
      args.includeSearch = false;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
  }

  return args;
}

function printHelp() {
  console.log(`
Usage:
  npm run scrape:papers -- [options]

Options:
  --keyword "北京 初三 一模 数学"        Run one keyword against configured search pages
  --keywords "kw1,kw2"                  Run several comma-separated keywords
  --search                              Also crawl configured search-result pages
  --no-search                           Only crawl curated first-tier pages (default)
  --max-pages 40                        Limit total fetched pages
  --delay-ms 800                        Polite delay between requests
  --output ./data/paper-scout.json      Result JSON path
`);
}

async function main() {
  const args = parseArgs(process.argv);
  const pages = buildPagePlan(args);
  const limitedPages = pages.slice(0, args.maxPages);
  const errors = [];
  const candidates = [];

  console.log(`Paper scout: fetching ${limitedPages.length} public pages from first-tier sources.`);

  for (const page of limitedPages) {
    try {
      const html = await fetchText(page.url);
      const pageCandidates = extractCandidates(html, page);
      candidates.push(...pageCandidates);
      console.log(`[${page.source.id}] ${pageCandidates.length} candidates <- ${page.url}`);
    } catch (error) {
      errors.push({ sourceId: page.source.id, url: page.url, message: error.message });
      console.warn(`[${page.source.id}] failed: ${page.url} (${error.message})`);
    }

    await delay(args.delayMs);
  }

  const deduped = dedupe(candidates)
    .map(enrichCandidate)
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.sourceId.localeCompare(b.sourceId));

  const payload = {
    generatedAt: new Date().toISOString(),
    sourcePolicy: "Public pages only. This script indexes metadata and links; it does not bypass login, payment, CAPTCHA, or download restrictions.",
    keywords: args.keywords,
    sources: SOURCES.map(({ id, name, priority }) => ({ id, name, priority })),
    stats: {
      fetchedPages: limitedPages.length,
      rawCandidates: candidates.length,
      results: deduped.length,
      errors: errors.length,
    },
    results: deduped,
    errors,
  };

  fs.mkdirSync(path.dirname(args.output), { recursive: true });
  fs.writeFileSync(args.output, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  console.log(`Saved ${deduped.length} results to ${args.output}`);
}

function buildPagePlan(args) {
  const pages = [];

  for (const source of SOURCES) {
    for (const url of source.urls || []) {
      pages.push({ source, url, kind: "curated" });
    }

    if (!args.includeSearch) continue;

    for (const template of source.searchTemplates || []) {
      for (const keyword of args.keywords) {
        pages.push({
          source,
          url: template.replace("{query}", encodeURIComponent(keyword)),
          kind: "search",
          keyword,
        });
      }
    }
  }

  return pages;
}

async function fetchText(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);

  try {
    const response = await fetch(url, {
      headers: {
        "user-agent": USER_AGENT,
        accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.7",
      },
      signal: controller.signal,
      redirect: "follow",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const buffer = Buffer.from(await response.arrayBuffer());
    const contentType = response.headers.get("content-type") || "";
    return decodeHtml(buffer, contentType);
  } catch (error) {
    const cause = error.cause ? `: ${error.cause.message || error.cause.code || error.cause}` : "";
    throw new Error(`${error.message}${cause}`);
  } finally {
    clearTimeout(timeout);
  }
}

function decodeHtml(buffer, contentType) {
  const declared = contentType.match(/charset=([^;\s]+)/i)?.[1];
  const probe = buffer.slice(0, 4096).toString("ascii");
  const meta = probe.match(/charset=["']?([a-zA-Z0-9_-]+)/i)?.[1];
  const encoding = normalizeEncoding(declared || meta || "utf-8");

  try {
    return new TextDecoder(encoding).decode(buffer);
  } catch {
    return new TextDecoder("utf-8").decode(buffer);
  }
}

function normalizeEncoding(encoding) {
  const value = encoding.toLowerCase();
  if (["gbk", "gb2312", "gb18030"].includes(value)) return "gb18030";
  return value;
}

function extractCandidates(html, page) {
  const title = stripTags(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] || "");
  const candidates = [];

  for (const link of extractLinks(html, page.url)) {
    const text = compactText(link.text || link.title || "");
    const haystack = `${text} ${link.href}`;

    if (!looksExamRelated(haystack)) continue;

    candidates.push({
      sourceId: page.source.id,
      sourceName: page.source.name,
      sourcePriority: page.source.priority,
      discoveryKind: page.kind,
      keyword: page.keyword || null,
      pageTitle: title,
      title: text || link.href,
      url: link.href,
      discoveredFrom: page.url,
    });
  }

  const pageText = compactText(stripTags(html));
  if (looksExamRelated(pageText)) {
    candidates.push({
      sourceId: page.source.id,
      sourceName: page.source.name,
      sourcePriority: page.source.priority,
      discoveryKind: page.kind,
      keyword: page.keyword || null,
      pageTitle: title,
      title: title || inferTitleFromUrl(page.url),
      url: page.url,
      discoveredFrom: page.url,
      snippet: pickSnippet(pageText),
    });
  }

  return candidates;
}

function extractLinks(html, baseUrl) {
  const links = [];
  const anchorRegex = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
  let match;

  while ((match = anchorRegex.exec(html))) {
    const attrs = match[1];
    const href = attrs.match(/\bhref\s*=\s*["']([^"']+)["']/i)?.[1];
    if (!href || href.startsWith("javascript:") || href.startsWith("#")) continue;

    const title = attrs.match(/\btitle\s*=\s*["']([^"']+)["']/i)?.[1] || "";

    try {
      links.push({
        href: new URL(href, baseUrl).toString(),
        title: decodeEntities(title),
        text: decodeEntities(stripTags(match[2])),
      });
    } catch {
      // Ignore malformed URLs from page chrome.
    }
  }

  return links;
}

function looksExamRelated(text) {
  return (
    containsAny(text, ["北京", ...DISTRICTS]) &&
    containsAny(text, EXAM_TYPES) &&
    containsAny(text, ["试卷", "试题", "真题", "答案", "PDF", "pdf"])
  );
}

function enrichCandidate(candidate) {
  const combined = `${candidate.title} ${candidate.pageTitle || ""} ${candidate.snippet || ""}`;
  const districts = tagsFrom(combined, DISTRICTS);
  const subjects = tagsFrom(combined, SUBJECTS);
  const examTypes = tagsFrom(combined, EXAM_TYPES);
  const grades = tagsFrom(combined, GRADES);
  const years = [...combined.matchAll(/\b20[2-3]\d\b/g)].map((match) => match[0]);

  return {
    ...candidate,
    districts,
    subjects,
    examTypes,
    grades,
    years: [...new Set(years)],
    score: scoreCandidate(candidate, { districts, subjects, examTypes, grades, years }),
  };
}

function scoreCandidate(candidate, tags) {
  let score = 100 - candidate.sourcePriority * 5;
  score += tags.examTypes.length * 12;
  score += tags.districts.length * 8;
  score += tags.subjects.length * 5;
  score += tags.grades.length * 4;
  score += tags.years.length * 3;
  if (/\.pdf(?:$|[?#])/i.test(candidate.url) || /PDF|pdf/.test(candidate.title)) score += 10;
  if (candidate.discoveryKind === "search") score += 5;
  return score;
}

function dedupe(items) {
  const seen = new Map();

  for (const item of items) {
    const key = normalizeUrl(item.url);
    const existing = seen.get(key);
    if (!existing || item.title.length > existing.title.length) {
      seen.set(key, item);
    }
  }

  return [...seen.values()];
}

function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    for (const key of [...parsed.searchParams.keys()]) {
      if (/^(utm_|spm|from|share)/i.test(key)) parsed.searchParams.delete(key);
    }
    return parsed.toString();
  } catch {
    return url;
  }
}

function tagsFrom(text, tags) {
  return tags.filter((tag) => text.includes(tag));
}

function containsAny(text, needles) {
  return needles.some((needle) => text.includes(needle));
}

function stripTags(value) {
  return value
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ");
}

function compactText(value) {
  return decodeEntities(value).replace(/\s+/g, " ").trim();
}

function decodeEntities(value) {
  return value
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number.parseInt(code, 10)));
}

function inferTitleFromUrl(url) {
  return new URL(url).pathname.split("/").filter(Boolean).at(-1) || url;
}

function pickSnippet(text) {
  const index = EXAM_TYPES.map((term) => text.indexOf(term)).find((item) => item >= 0) || 0;
  return text.slice(Math.max(0, index - 80), index + 220);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
