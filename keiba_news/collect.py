"""Google ニュース RSS から競馬ニュースを集め、data/articles.json に蓄積する。"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import config

GNEWS_URL = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 (compatible; keiba-news-watch/1.0)"

# 見出しの末尾に付く媒体名などを取り除く
_SUFFIX_PATTERNS = [
    re.compile(r"\s*\|\s*[^|]*$"),          # "| 競馬ニュース - netkeiba"
    re.compile(r"\s*[（(][^（）()]{1,20}[）)]\s*$"),  # "（日刊スポーツ）"
]


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def clean_title(raw_title: str, source: str) -> str:
    """'見出し - 媒体名' の媒体名部分を落とす。"""
    t = normalize(raw_title)
    src = normalize(source)
    if src and t.endswith(" - " + src):
        t = t[: -len(" - " + src)]
    # Yahoo!ニュース経由の記事は "（媒体）" が付く
    t = re.sub(r"\s+-\s+Yahoo!ニュース$", "", t)
    for pat in _SUFFIX_PATTERNS:
        t = pat.sub("", t)
    # netkeiba などは "見出し - netkeiba - netkeiba" と媒体名が重なることがある
    while src and t.endswith(" - " + src):
        t = t[: -len(" - " + src)]
    return t.strip()


def dedupe_key(title: str) -> str:
    t = normalize(title)
    t = re.sub(r"[\s　・、。!！?？「」『』【】\[\]()（）\"'`~〜\-—|:：/／]", "", t)
    return t.lower()


def build_url(query: str) -> str:
    q = f"{query} {config.QUERY_WINDOW}".strip()
    params = {"q": q, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    return GNEWS_URL + "?" + urllib.parse.urlencode(params)


def fetch(url: str, retries: int = 3, timeout: int = 20) -> bytes:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except Exception as e:  # noqa: BLE001 - ネットワーク例外はまとめて再試行
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"取得に失敗しました: {url}: {last}")


def parse_feed(xml_bytes: bytes, query: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        source = normalize(it.findtext("source") or "")
        raw_title = it.findtext("title") or ""
        title = clean_title(raw_title, source)
        pub = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
        except (TypeError, ValueError):
            dt = None
        if not title or dt is None:
            continue
        items.append({
            "title": title,
            "url": (it.findtext("link") or "").strip(),
            "source": source,
            "published": dt.isoformat(),
            "queries": [query],
        })
    return items


def is_excluded(article: dict) -> bool:
    if article["source"] in config.EXCLUDE_SOURCES:
        return True
    title = article["title"]
    if "JRA" in title or "中央競馬" in title:
        return False
    return any(k in title for k in config.EXCLUDE_IF_NO_JRA)


def merge(existing: list[dict], new: list[dict], now: datetime) -> list[dict]:
    """重複を除いて結合し、保存期間を過ぎたものを捨てる。"""
    by_key: dict[str, dict] = {}
    for a in existing + new:
        key = dedupe_key(a["title"])
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = dict(a, sources=sorted({a["source"], *a.get("sources", [])} - {""}))
            continue
        cur["queries"] = sorted(set(cur.get("queries", [])) | set(a.get("queries", [])))
        cur["sources"] = sorted(set(cur.get("sources", [])) | {a["source"]} - {""})
        # 一番早い配信時刻を採用する
        if a["published"] < cur["published"]:
            cur["published"] = a["published"]
    cutoff = (now - timedelta(days=config.RETENTION_DAYS)).isoformat()
    out = [a for a in by_key.values() if a["published"] >= cutoff and not is_excluded(a)]
    out.sort(key=lambda a: a["published"], reverse=True)
    return out


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("articles", [])


def save(path: Path, articles: list[dict], now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated": now.isoformat(), "articles": articles}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def collect(path: Path, now: datetime | None = None, fetcher=fetch) -> tuple[list[dict], dict]:
    now = now or datetime.now(timezone.utc)
    fresh: list[dict] = []
    stats = {"queries": 0, "fetched": 0, "errors": []}
    for q in config.QUERIES:
        try:
            items = parse_feed(fetcher(build_url(q)), q)
        except Exception as e:  # noqa: BLE001 - 1 クエリの失敗で全体を止めない
            stats["errors"].append(f"{q}: {e}")
            continue
        stats["queries"] += 1
        stats["fetched"] += len(items)
        fresh.extend(items)
    if stats["queries"] == 0:
        raise RuntimeError("すべてのクエリで取得に失敗しました: " + "; ".join(stats["errors"]))
    articles = merge(load(path), fresh, now)
    save(path, articles, now)
    stats["stored"] = len(articles)
    return articles, stats
