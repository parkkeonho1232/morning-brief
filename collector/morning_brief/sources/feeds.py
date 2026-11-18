"""RSS · 뉴스 사이트맵 · Google 뉴스 RSS 수집. 제목·링크·발행시각·피드 제공 요약만 다룬다."""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from ..config import Source
from ..pipeline.normalize import KST, canonical_url, clean_summary, clean_text, parse_dt

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass
class FetchedItem:
    url: str
    title: str
    summary: str | None
    published_at: datetime | None    # None: 피드에 발행시각 없음 (Nikkei)


@dataclass
class FetchResult:
    status: int                      # 200, 304
    items: list[FetchedItem]
    etag: str | None = None
    last_modified: str | None = None


def fetch(client: httpx.Client, source: Source, feed_url: str,
          etag: str | None = None, last_modified: str | None = None) -> FetchResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    r = client.get(feed_url, headers=headers)
    if r.status_code == 304:
        return FetchResult(304, [], etag, last_modified)
    r.raise_for_status()
    parse = {"rss": parse_rss, "sitemap": parse_sitemap, "gnews": parse_gnews}[source.method]
    items = parse(r.content, source)
    return FetchResult(r.status_code, items, r.headers.get("ETag"), r.headers.get("Last-Modified"))


def _naive_tz(source: Source):
    # 시간대 표기가 없는 피드: 국내는 KST, 해외는 UTC로 간주
    return KST if source.tz_naive or source.region == "domestic" else timezone.utc


def parse_rss(body: bytes, source: Source) -> list[FetchedItem]:
    feed = feedparser.parse(body)
    out = []
    for e in feed.entries:
        title, link = clean_text(e.get("title")), e.get("link")
        if not title or not link:
            continue
        summary = None
        if source.has_summary:
            raw = e.get("summary")
            if not clean_text(raw) and e.get("content"):
                raw = e["content"][0].get("value")       # 뉴스1: content:encoded 리드
            summary = clean_summary(raw)
        published = parse_dt(e.get("published") or e.get("updated"), _naive_tz(source))
        out.append(FetchedItem(canonical_url(link), title, summary, published))
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(body: bytes, source: Source) -> list[FetchedItem]:
    root = ET.fromstring(body.lstrip())
    out = []
    for url_el in root:
        if _local(url_el.tag) != "url":
            continue
        fields = {}
        for el in url_el.iter():
            fields.setdefault(_local(el.tag), (el.text or "").strip())
        title = clean_text(fields.get("title"))
        published = parse_dt(fields.get("publication_date") or fields.get("lastmod"), _naive_tz(source))
        if title and fields.get("loc") and published:
            out.append(FetchedItem(canonical_url(fields["loc"]), title, None, published))
    return out


def parse_gnews(body: bytes, source: Source) -> list[FetchedItem]:
    """Google 뉴스 RSS: 링크는 Google 경유 주소. 제목 끝 ' - 매체명' 제거, 요약 없음."""
    feed = feedparser.parse(body)
    out = []
    for e in feed.entries:
        title, link = clean_text(e.get("title")), e.get("link")
        published = parse_dt(e.get("published"), timezone.utc)
        if not title or not link or not published:
            continue
        outlet = clean_text((e.get("source") or {}).get("title"))
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3].rstrip()
        out.append(FetchedItem(link, title, None, published))
    return out
