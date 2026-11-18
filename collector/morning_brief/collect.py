"""매시간 수집: 피드 → 정규화 → article 적재. feed_state로 피드당 최소 간격·조건부 요청·누락/중단을 관리한다."""
import json
import time as _time
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import psycopg

from . import config, db
from .deliver import telegram
from .pipeline.normalize import is_junk_title, title_hash
from .pipeline.normalize import KST
from .pipeline import translate
from .sources import schedules, youtube
from .sources.feeds import FetchResult, fetch

COLLECTABLE = ("rss", "sitemap", "gnews")
FAILURE_ALERT_AT = 3          # 연속 실패 3회째에 한 번 알림
CRON_JITTER = timedelta(minutes=5)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.user_agent()}, timeout=httpx.Timeout(20.0, connect=10.0),
                        follow_redirects=True)


def _targets():
    for s in config.sources():
        if s.method in COLLECTABLE:
            for url in s.feed_urls:
                yield s, url


def _fetch_all(jobs):
    """jobs: [(source, url, state)] → [(source, url, state, FetchResult | Exception)]"""
    with _client() as client, ThreadPoolExecutor(8) as pool:
        def one(job):
            s, url, st = job
            try:
                return (*job, fetch(client, s, url, st.get("etag"), st.get("last_modified")))
            except Exception as e:
                return (*job, e)
        return list(pool.map(one, jobs))


def sync_config(conn) -> int:
    """sources.yaml → source 테이블. grp는 대시보드에서 PD가 바꿀 수 있으므로 비어 있을 때만 채운다."""
    n = 0
    for s in config.sources():
        conn.execute("""
            insert into source (name, region, lang, grp, method, feed_urls, paywall, has_summary, tz_naive, active)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (name) do update set
              region = excluded.region, lang = excluded.lang, grp = coalesce(source.grp, excluded.grp),
              method = excluded.method, feed_urls = excluded.feed_urls, paywall = excluded.paywall,
              has_summary = excluded.has_summary, tz_naive = excluded.tz_naive, active = excluded.active
        """, (s.name, s.region, s.lang, s.grp, s.method, list(s.feed_urls), s.paywall, s.has_summary,
              s.tz_naive, s.method != "none"))
        n += 1
    yt = config.load("youtube_channels")
    for kind, key in (("sisa", "channels"), ("news", "news_channels")):
        for c in yt.get(key) or []:
            conn.execute("""
                insert into yt_channel (id, handle, name, kind, source_name) values (%s, %s, %s, %s, %s)
                on conflict (id) do update set handle = excluded.handle, name = excluded.name,
                  kind = excluded.kind, source_name = excluded.source_name
            """, (c["channel_id"], c.get("handle"), c.get("name"), kind, c.get("source")))
    conn.commit()
    return n


def _started_at(conn) -> datetime:
    row = conn.execute("select value from app_meta where key = 'collect_started_at'").fetchone()
    if row:
        return datetime.fromisoformat(row["value"])
    now = datetime.now(timezone.utc)
    conn.execute("insert into app_meta (key, value) values ('collect_started_at', %s)", (now.isoformat(),))
    conn.commit()
    return now


def run() -> int:
    t0 = _time.monotonic()
    interval = timedelta(minutes=config.ops()["collect"]["interval_min"])
    now = datetime.now(timezone.utc)
    with db.connect() as conn:
        sync_config(conn)
        started_at = _started_at(conn)
        log_id = conn.execute("insert into run_log (job, step) values ('collect', 'fetch') returning id").fetchone()["id"]
        conn.commit()

        src_ids = {r["name"]: r["id"] for r in conn.execute("select id, name from source")}
        states = {r["feed_url"]: r for r in conn.execute("select * from feed_state")}
        jobs = []
        for s, url in _targets():
            st = states.get(url) or {}
            if st.get("last_fetch_at") and now - st["last_fetch_at"] < interval - CRON_JITTER:
                continue
            jobs.append((s, url, st))

        detail = {"feeds": len(jobs), "new": 0, "errors": {}, "gaps": [], "per_source": {}}
        alerts = []
        print(f"collect: 대상 피드 {len(jobs)}개 ({_time.monotonic() - t0:.0f}s)")
        for s, url, st, res in _fetch_all(jobs):
            sid = src_ids[s.name]
            if isinstance(res, Exception):
                fails = (st.get("consecutive_failures") or 0) + 1
                err = f"{type(res).__name__}: {str(res)[:200]}"
                detail["errors"][url] = err
                if fails == FAILURE_ALERT_AT:
                    alerts.append(f"⚠️ 수집 {fails}회 연속 실패: {s.name}\n{url}\n{err}")
                _upsert_state(conn, url, sid, now, ok=False, fails=fails, error=err)
                conn.commit()
                continue
            first_fetch = not st.get("last_ok_at")
            baseline = [i.url for i in res.items if i.published_at is None] if first_fetch else None
            new = _store(conn, s, sid, res, started_at, now, set(baseline or st.get("baseline_urls") or ()))
            dated = [i.published_at for i in res.items if i.published_at]
            if dated and st.get("newest_published_at") and min(dated) > st["newest_published_at"]:
                detail["gaps"].append({"feed": url, "since": st["newest_published_at"].isoformat(),
                                       "oldest_in_feed": min(dated).isoformat()})
            _upsert_state(conn, url, sid, now, ok=True, result=res, newest=max(dated, default=None),
                          baseline=baseline)
            conn.execute("update source set last_ok_at = %s where id = %s", (now, sid))
            conn.commit()
            detail["new"] += new
            detail["per_source"][s.name] = detail["per_source"].get(s.name, 0) + new

        print(f"collect: 피드 수집·저장 끝 new={detail['new']} ({_time.monotonic() - t0:.0f}s)")
        for name, job in (("youtube", _youtube), ("schedules", _schedules), ("translate", _translate)):
            print(f"collect: {name} 시작 ({_time.monotonic() - t0:.0f}s)")
            try:
                detail[name] = job(conn, now)
            except Exception as e:
                conn.rollback()
                detail[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                detail["errors"][name] = detail[name]["error"]
            conn.commit()

        alerts += _stale_sources(conn, started_at, now)
        conn.execute("update run_log set finished_at = now(), ok = %s, detail = %s where id = %s",
                     (not detail["errors"], json.dumps(detail, ensure_ascii=False), log_id))
        conn.commit()

    for a in alerts:
        telegram.send(a, alert=True)
    print(f"collect: feeds={detail['feeds']} new={detail['new']} errors={len(detail['errors'])} gaps={len(detail['gaps'])}")
    for name in ("youtube", "schedules", "translate"):
        if name in detail:
            print(f"  {name}: {json.dumps(detail[name], ensure_ascii=False)}")
    for url, err in detail["errors"].items():
        print(f"  error {url}\n        {err}")
    for g in detail["gaps"]:
        print(f"  gap   {g['feed']} since={g['since']} oldest_in_feed={g['oldest_in_feed']}")
    return 0


def _store(conn, s, sid, res: FetchResult, started_at, now, baseline: set[str]) -> int:
    """피드 하나를 쿼리 한 번으로 저장 (항목마다 왕복하면 수천 번이라 수집이 15~20분 걸렸다)."""
    rows, seen = [], set()
    for it in res.items:
        if is_junk_title(it.title):
            continue
        if it.published_at is None:
            # 발행시각 없는 피드: 처음 본 시각을 발행시각으로. 첫 수집 때 이미 있던 기사는 백필이라 제외
            if it.url in baseline:
                continue
            it.published_at = now
        # 가동 이전 기사(백필) 제외, 시간대 오류로 미래 시각인 기사 제외
        if it.published_at < started_at or it.published_at > now + timedelta(hours=1):
            continue
        h = title_hash(it.title)
        if h in seen or it.url in seen:            # 같은 피드 안 중복 (같은 제목·같은 URL)
            continue
        seen |= {h, it.url}
        rows.append((it.url, it.title, it.summary, it.published_at, h))
    if not rows:
        return 0
    u, t, sm, p, h = (list(c) for c in zip(*rows))
    try:
        with conn.transaction():                   # 실패하면 이 피드만 되돌리고 한 건씩 저장으로
            return _store_batch(conn, s, sid, u, t, sm, p, h)
    except psycopg.Error as e:
        print(f"collect: 일괄 저장 실패 → 한 건씩 ({type(e).__name__}: {str(e)[:150]})")
    new = 0
    for r in rows:
        new += _store_batch(conn, s, sid, *([x] for x in r))
    return new


def _store_batch(conn, s, sid, u, t, sm, p, h) -> int:
    cur = conn.execute("""
        insert into article (source_id, url, title, summary, published_at, lang, via, title_hash)
        select %s, x.u, x.t, x.sm, x.p, %s, %s, x.h
        from unnest(%s::text[], %s::text[], %s::text[], %s::timestamptz[], %s::text[]) as x(u, t, sm, p, h)
        where not exists (select 1 from article a where a.source_id = %s and a.title_hash = x.h
                          and a.published_at > x.p - interval '3 days')
        on conflict (url) do nothing
    """, (sid, s.lang, s.method, u, t, sm, p, h, sid))
    return cur.rowcount


def _youtube(conn, now) -> dict:
    """채널별 최근 업로드 등록 + 게시 48시간 이내 영상 조회수 스냅샷."""
    if not os.environ.get("YOUTUBE_API_KEY"):
        return {"skipped": "YOUTUBE_API_KEY 없음"}
    channels = [r["id"] for r in conn.execute("select id from yt_channel where active")]
    new_videos = 0
    with _client() as client:
        for cid in channels:
            for v in youtube.recent_uploads(client, cid):
                cur = conn.execute("""
                    insert into yt_video (id, channel_id, title, published_at) values (%s, %s, %s, %s)
                    on conflict (id) do update set title = excluded.title
                    returning (xmax = 0) as inserted
                """, (v.id, v.channel_id, v.title, v.published_at))
                new_videos += cur.fetchone()["inserted"]
        track = [r["id"] for r in conn.execute(
            "select id from yt_video where published_at > %s", (now - timedelta(hours=youtube.TRACK_HOURS),))]
        counts = youtube.view_counts(client, track) if track else {}
    if counts:                                  # 조회수 스냅샷은 한 번에 (영상 1,500개를 하나씩 넣으면 5분)
        conn.execute("""insert into yt_stat (video_id, captured_at, views)
                        select v, %s, n from unnest(%s::text[], %s::bigint[]) as x(v, n) on conflict do nothing""",
                     (now, list(counts), list(counts.values())))
    return {"channels": len(channels), "new_videos": new_videos, "snapshots": len(counts)}


def _translate(conn, now) -> dict:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY")):
        return {"skipped": "LLM 키 없음"}
    from . import llm
    out = translate.run(conn, now)
    out["llm"] = llm.usage.calls
    return out


def _schedules(conn, now) -> dict:
    """공식 일정: 하루 1회만 갱신 (PD 승인 범위). 국회는 조회 범위의 미래 일정을 통째로 교체."""
    row = conn.execute("select value from app_meta where key = 'schedules_at'").fetchone()
    if row and now - datetime.fromisoformat(row["value"]) < timedelta(hours=20):
        return {"skipped": "오늘 이미 갱신"}
    out = {}
    items = schedules.bok_mpc() + schedules.manual()
    if os.environ.get("ASSEMBLY_API_KEY"):
        days = config.ops()["schedules"].get("assembly_days_ahead", 14)
        today = now.astimezone(KST).date()
        with _client() as client:
            assembly = schedules.assembly(client, today, days)
        conn.execute("delete from schedule where org = '국회' and starts_at >= %s",
                     (datetime.combine(today, datetime.min.time(), KST),))
        items += assembly
        out["국회"] = len(assembly)
    for s in items:
        conn.execute("""
            insert into schedule (org, title, starts_at, url, all_day, kind, place, host, fetched_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (org, title, starts_at) do update set url = excluded.url, all_day = excluded.all_day,
              kind = excluded.kind, place = excluded.place, host = excluded.host, fetched_at = excluded.fetched_at
        """, (s.org, s.title, s.starts_at, s.url, s.all_day, s.kind, s.place, s.host, now))
    conn.execute("""insert into app_meta (key, value) values ('schedules_at', %s)
                    on conflict (key) do update set value = excluded.value""", (now.isoformat(),))
    out["total"] = len(items)
    return out


def _upsert_state(conn, url, sid, now, ok, result=None, newest=None, baseline=None, fails=0, error=None):
    if ok:
        conn.execute("""
            insert into feed_state (feed_url, source_id, etag, last_modified, last_fetch_at, last_ok_at,
                                    last_item_count, newest_published_at, consecutive_failures, last_error,
                                    baseline_urls)
            values (%s, %s, %s, %s, %s, %s, %s, %s, 0, null, coalesce(%s::text[], '{}'))
            on conflict (feed_url) do update set
              etag = excluded.etag, last_modified = excluded.last_modified, last_fetch_at = excluded.last_fetch_at,
              last_ok_at = excluded.last_ok_at,
              last_item_count = case when %s = 304 then feed_state.last_item_count else excluded.last_item_count end,
              newest_published_at = coalesce(excluded.newest_published_at, feed_state.newest_published_at),
              consecutive_failures = 0, last_error = null,
              baseline_urls = coalesce(%s::text[], feed_state.baseline_urls)
        """, (url, sid, result.etag, result.last_modified, now, now, len(result.items), newest, baseline,
              result.status, baseline))
    else:
        conn.execute("""
            insert into feed_state (feed_url, source_id, last_fetch_at, consecutive_failures, last_error)
            values (%s, %s, %s, %s, %s)
            on conflict (feed_url) do update set last_fetch_at = excluded.last_fetch_at,
              consecutive_failures = excluded.consecutive_failures, last_error = excluded.last_error
        """, (url, sid, now, fails, error))


def _stale_sources(conn, started_at, now) -> list[str]:
    """24시간 새 기사 0건인 매체를 하루 한 번 알린다."""
    if now - started_at < timedelta(hours=24):
        return []
    key = f"alert_stale_{now.astimezone(timezone(timedelta(hours=9))):%Y%m%d}"
    if conn.execute("select 1 from app_meta where key = %s", (key,)).fetchone():
        return []
    rows = conn.execute("""
        select s.name from source s
        where s.active and s.method in ('rss','sitemap','gnews')
          and not exists (select 1 from article a where a.source_id = s.id and a.collected_at > %s)
        order by s.name
    """, (now - timedelta(hours=24),)).fetchall()
    conn.execute("insert into app_meta (key, value) values (%s, %s)", (key, now.isoformat()))
    conn.commit()
    if not rows:
        return []
    return ["⚠️ 24시간 새 기사 0건: " + ", ".join(r["name"] for r in rows)]


def dry_run() -> int:
    """DB 없이 모든 피드를 받아 매체별 결과만 출력한다."""
    jobs = [(s, url, {}) for s, url in _targets()]
    by_source: dict[str, list] = {}
    for s, url, _, res in _fetch_all(jobs):
        by_source.setdefault(s.name, []).append((url, res))
    failed = 0
    for name, results in by_source.items():
        items = [i for _, r in results if not isinstance(r, Exception) for i in r.items]
        errs = [f"{u}: {r}" for u, r in results if isinstance(r, Exception)]
        failed += bool(errs)
        newest = max((i.published_at for i in items if i.published_at), default=None)
        with_sum = sum(1 for i in items if i.summary)
        mark = "✗" if errs else "✓"
        print(f"{mark} {name:<16} feeds={len(results)} items={len(items):<4} summary={with_sum:<4} "
              f"newest={newest.astimezone(timezone(timedelta(hours=9))):%m-%d %H:%M}" if newest else
              f"{mark} {name:<16} feeds={len(results)} items={len(items)}")
        for e in errs:
            print(f"    {e[:160]}")
        if items:
            print(f"    e.g. {items[0].title[:70]}")
    return 1 if failed else 0
