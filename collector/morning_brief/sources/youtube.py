"""YouTube Data API: 지정 채널의 새 영상 + 게시 48시간 이내 영상의 시간별 조회수 스냅샷.

할당량: playlistItems.list 1유닛/채널, videos.list 50개당 1유닛 → 16채널 매시간 ≈ 하루 500유닛.
채널 RSS(/feeds/videos.xml)는 youtube.com robots.txt Disallow라 쓰지 않는다.
"""
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..pipeline.normalize import clean_text, parse_dt

API = "https://www.googleapis.com/youtube/v3"
TRACK_HOURS = 48          # 기준선 체크포인트(6h·24h)를 넉넉히 덮는 추적 기간


@dataclass
class Video:
    id: str
    channel_id: str
    title: str
    published_at: datetime


def _get(client: httpx.Client, path: str, **params) -> dict:
    r = client.get(f"{API}/{path}", params={**params, "key": os.environ["YOUTUBE_API_KEY"]})
    if not r.is_success:
        # 응답 본문에 키가 섞이지 않도록 메시지만
        msg = r.json().get("error", {}).get("message", "") if r.headers.get("content-type", "").startswith("application/json") else ""
        raise RuntimeError(f"YouTube {path} HTTP {r.status_code} {msg[:150]}")
    return r.json()


def recent_uploads(client: httpx.Client, channel_id: str, max_results: int = 10) -> list[Video]:
    uploads = "UU" + channel_id[2:]                      # 채널의 업로드 재생목록
    data = _get(client, "playlistItems", part="snippet,contentDetails", playlistId=uploads,
                maxResults=max_results)
    out = []
    for it in data.get("items", []):
        vid = it["contentDetails"]["videoId"]
        published = parse_dt(it["contentDetails"].get("videoPublishedAt") or it["snippet"].get("publishedAt"))
        title = clean_text(it["snippet"].get("title"))
        if published and title and title not in ("Private video", "Deleted video"):
            out.append(Video(vid, channel_id, title, published))
    return out


def view_counts(client: httpx.Client, video_ids: list[str]) -> dict[str, int]:
    out = {}
    for i in range(0, len(video_ids), 50):
        data = _get(client, "videos", part="statistics", id=",".join(video_ids[i:i + 50]), maxResults=50)
        for it in data.get("items", []):
            views = it.get("statistics", {}).get("viewCount")
            if views is not None:
                out[it["id"]] = int(views)
    return out


def search(client: httpx.Client, query: str, published_after: datetime, max_results: int = 30) -> list[dict]:
    """사건 키워드로 최근 영상 검색 (search.list 100유닛/회) → 조회수 순.

    카드 10장 × 1회 = 하루 약 1,000유닛. 무료 할당량 10,000유닛 안에서 매시간 수집과 함께 쓴다.
    """
    data = _get(client, "search", part="snippet", q=query, type="video", maxResults=max_results,
                order="relevance", regionCode="KR", relevanceLanguage="ko",
                publishedAfter=published_after.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    items = []
    for it in data.get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        sn = it.get("snippet") or {}
        if vid and sn.get("title"):
            items.append({"id": vid, "title": clean_text(sn["title"]), "channel_id": sn.get("channelId"),
                          "channel": clean_text(sn.get("channelTitle") or "")})
    views = view_counts(client, [x["id"] for x in items]) if items else {}
    for x in items:
        x["views"] = views.get(x["id"])
        x["url"] = f"https://www.youtube.com/watch?v={x['id']}"
    return sorted(items, key=lambda x: x["views"] or 0, reverse=True)
