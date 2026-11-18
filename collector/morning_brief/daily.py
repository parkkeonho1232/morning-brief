"""매일 05:30 KST 배치: 번역 마무리 → 임베딩 → 묶기 → 사건 연결 → 변화 감지 → 점수화 → 카드 → 브리핑.

같은 기준일을 다시 돌려도 결과가 겹치지 않도록 그날 만든 묶음·사건·사실을 먼저 지운다.
"""
import json
import re
import os
import time as _time
from datetime import date, datetime, time, timedelta, timezone

import httpx
import numpy as np

from . import config, db, llm
from .deliver import briefing, telegram
from .deliver import email as mail
from .pipeline import cards as cd
from .pipeline import cluster as cl
from .pipeline import score as sc
from .pipeline import events as ev
from .pipeline import facts as fx
from .pipeline import translate
from .pipeline.normalize import KST, is_junk_title
from .sources import youtube


def window(base_date: date) -> tuple[datetime, datetime]:
    w = config.ops()["daily"]["window"]
    h, m = map(int, w["to"].split(":"))
    end = datetime.combine(base_date, time(h, m), KST)
    return end - timedelta(days=1), end


EMBED_CACHE = os.path.expanduser(os.environ.get("EMBED_CACHE", "~/.cache/morning-brief/articles-bge-m3.npz"))
EMBED_CACHE_KEEP = 20000          # 최근 기사 id 기준 (하루 6~7천 건 → 약 3일치)


def embed_articles(articles: list[cl.Article]) -> tuple[np.ndarray, str]:
    """기사 벡터는 bge-m3로 한 번 계산하면 파일 캐시(GitHub Actions cache)에 두고 다시 쓴다.

    CPU 임베딩이 배치 시간의 대부분이라, 오후 업데이트·다음 날 아침 배치가 같은 기사를 다시 계산하지 않게 한다.
    예비 모델(Gemini)로 넘어가면 모델을 섞지 않도록 전부 새로 계산하고 캐시는 건드리지 않는다.
    """
    texts = [f"{a.title}. {a.summary or ''}"[:500] for a in articles]
    cache: dict[int, np.ndarray] = {}
    try:
        with np.load(EMBED_CACHE) as z:
            cache = dict(zip(z["ids"].tolist(), z["vecs"]))
    except (OSError, KeyError, ValueError):
        pass
    missing = [i for i, a in enumerate(articles) if a.id not in cache]
    for n in range(0, len(missing), 1000):     # 1000건마다 저장 → 시간 초과로 끊겨도 다음 실행이 이어서 쓴다
        part = missing[n:n + 1000]
        new, model = llm.embed([texts[i] for i in part])
        if model != "bge-m3":
            return llm.embed(texts, force_model=model)
        cache.update({articles[i].id: v for i, v in zip(part, new)})
        keep = sorted(cache)[-EMBED_CACHE_KEEP:]
        os.makedirs(os.path.dirname(EMBED_CACHE), exist_ok=True)
        np.savez(EMBED_CACHE, ids=np.array(keep, dtype=np.int64), vecs=np.stack([cache[k] for k in keep]))
        print(f"embed: {min(n + 1000, len(missing))}/{len(missing)}")
    print(f"embed: {len(articles)}건 중 캐시 {len(articles) - len(missing)} · 새로 계산 {len(missing)}")
    if not articles:
        return np.zeros((0, llm.EMBED_DIM), dtype=np.float32), "bge-m3"
    return np.stack([cache[a.id] for a in articles]).astype(np.float32), "bge-m3"


def reset_day(conn, d: date):
    conn.execute("delete from card where base_date = %s", (d,))
    conn.execute("update article set cluster_id = null where cluster_id in (select id from cluster where base_date = %s)", (d,))
    conn.execute("delete from cluster where base_date = %s", (d,))
    conn.execute("delete from event_snapshot where base_date = %s", (d,))
    conn.execute("delete from event_fact where first_seen_date = %s", (d,))
    # 오후 업데이트 카드(전날 기준일)가 가리키던 임시 사건은 카드 본문에만 남긴다
    conn.execute("update card set event_id = null where event_id in (select id from event where first_seen_date = %s)", (d,))
    conn.execute("delete from event where first_seen_date = %s", (d,))
    conn.execute("""update event e set last_change_date =
                      (select max(first_seen_date) from event_fact f where f.event_id = e.id)
                    where last_change_date >= %s""", (d,))


def load_articles(conn, start: datetime, end: datetime) -> list[cl.Article]:
    rows = conn.execute("""
        select a.id, a.source_id, s.name as source, s.grp, s.region,
               coalesce(a.title_ko, a.title) as title, coalesce(a.summary_ko, a.summary) as summary, a.published_at
        from article a join source s on s.id = a.source_id
        where a.published_at >= %s and a.published_at < %s
        order by a.published_at
    """, (start, end)).fetchall()
    return [cl.Article(**r) for r in rows if not is_junk_title(r["title"])]


# 언론사·방송사 채널은 섭외 후보가 아니므로 뺀다 (유튜버·시사 프로그램 채널만 남김)
PRESS = ("뉴스", "news", "연합", "신문", "일보", "방송", "tv조선", "mbn", "ytn", "kbs", "mbc", "sbs", "jtbc", "obs",
         "채널a", "dmb", "경제tv", "한국경제", "매일경제", "서울경제", "머니투데이", "이데일리", "헤럴드", "브리핑")
_HANGUL = re.compile(r"[가-힣]")


def is_press(channel: str) -> bool:
    c = channel.lower().replace(" ", "")
    return any(k in c for k in PRESS)


SCREEN_PROMPT = """시사 방송 섭외 참고용으로 유튜브 영상 제목을 점검한다. 각 항목은 사건 제목과 영상 제목이다.
1. keep: 영상이 그 사건을 실제로 다루면 true, 관계없으면 false.
2. title: 영상 제목을 그대로 두되, 공인이 아닌 일반인(피의자·피해자·수험생·제보자 등)의 실명이 있으면 "A씨"로 바꾼다.
   정치인·공직자·기업 대표·유명인 이름은 그대로 둔다. 다른 말은 바꾸지 않는다.
출력: {{"items": [{{"k": "항목 키", "keep": true, "title": "…"}}]}}

항목:
{items}
"""


def _screen_videos(cards: list[dict]) -> str:
    """검색으로 찾은 영상 제목을 한 번에 점검: 관계없는 영상 제거 + 일반인 실명 가리기 (lite 1회).

    실패하면 검색 영상의 제목을 지우고 채널·링크만 남긴다 (실명 노출을 막는 쪽으로).
    """
    items = {f"c{i}v{j}": (b, v) for i, b in enumerate(cards)
             for j, v in enumerate(b.get("videos") or []) if v.get("via") == "search"}
    if not items:
        return "none"
    payload = [{"k": k, "event": b["title"], "video": v["title"]} for k, (b, v) in items.items()]
    try:
        out = llm.generate_json(SCREEN_PROMPT.format(items=json.dumps(payload, ensure_ascii=False)), tier="lite")
        res = {r.get("k"): r for r in (out.get("items") or []) if isinstance(r, dict)} if isinstance(out, dict) else {}
    except llm.LLMError as e:
        print(f"youtube: 제목 점검 실패 {str(e)[:120]}")
        res = {}
    for k, (b, v) in items.items():
        r = res.get(k)
        if r is None:
            v["title"] = None
        elif r.get("keep") is False:
            v["drop"] = True
        elif isinstance(r.get("title"), str) and 0 < len(r["title"]) <= len(v["title"]) + 20:
            v["title"] = r["title"].strip()
    for b in cards:
        b["videos"] = [v for v in b.get("videos") or [] if not v.pop("drop", False)][:5]
    return "ok" if res else "titles_hidden"


def youtube_search(cards: list[dict], d: date) -> dict:
    """최종 카드마다 유튜브 검색 1회 → 이 사건을 다룬 영상·채널 (방송사 뉴스 채널은 제외, 조회수 순 5개).

    감시 채널(시사 8개)의 임베딩 매칭 결과와 합친다. 할당량 초과 등 실패하면 그 카드만 건너뛴다.
    """
    if not os.environ.get("YOUTUBE_API_KEY"):
        return {"yt_searched": 0}
    news = {c["channel_id"] for c in config.load("youtube_channels").get("news_channels") or []}
    since = datetime.combine(d - timedelta(days=3), time(0, 0), KST)
    done, failed = 0, 0
    with httpx.Client(timeout=20) as client:
        for b in cards:
            q = b.get("yt_query") or b["title"]
            try:
                found = youtube.search(client, q, since)
                done += 1
            except Exception as e:
                failed += 1
                print(f"youtube: 검색 실패 '{q}' {str(e)[:120]}")
                continue
            have = {v["url"] for v in b.get("videos") or []}
            extra = [{"channel": v["channel"], "title": v["title"], "url": v["url"], "views": v["views"],
                      "via": "search"} for v in found
                     if v["channel_id"] not in news and v["url"] not in have and not is_press(v["channel"])
                     and _HANGUL.search(v["title"])]
            b["videos"] = sorted((b.get("videos") or []) + extra, key=lambda v: v.get("views") or 0, reverse=True)[:8]
    screened = _screen_videos(cards)
    return {"yt_searched": done, "yt_failed": failed, "yt_screen": screened}


def build_cards(conn, d: date, model: str, cfg: dict, start: datetime, end: datetime,
                limit: int) -> tuple[list[dict], int, int]:
    cands = sc.candidates(conn, d)
    sc.attach_schedules(conn, cands, d, model)
    sc.attach_videos(conn, cands, start, end, model)
    sc.base_scores(cands, d)
    pool = sorted(cands, key=lambda c: c.base_score, reverse=True)[:limit]
    built, failed = [], 0
    for c in pool:
        try:
            card = cd.build(conn, c, d)
        except llm.LLMError as e:
            failed += 1
            print(f"cards: 실패 event={c.event_id} {str(e)[:150]}")
            continue
        if card:
            built.append(card)
    return built, len(cands), failed


def rank(cards: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    """Top 5 = 중요도 순 상위 5, 더 볼 만한 소재 = 그다음 5."""
    max_base = max((b["score"]["base"] for b in cards), default=1) or 1
    for b in cards:
        b["score"]["top"] = round(b["score"]["base"] / max_base + 1.5 * b["score"]["importance"], 3)
    ranked = sorted(cards, key=lambda b: b["score"]["top"], reverse=True)
    return ranked[:5], ranked[5:10]


def save_cards(conn, d: date, top: list[dict], ext: list[dict]):
    conn.execute("delete from card where base_date = %s", (d,))
    for kind, cards in (("top", top), ("extension", ext)):
        for r, b in enumerate(cards, 1):
            conn.execute("""insert into card (base_date, event_id, rank, kind, body)
                            values (%s, (select id from event where id = %s), %s, %s, %s)""",
                         (d, b["event_id"], r, kind,
                          json.dumps(b, ensure_ascii=False, default=str)))


def make_cards(conn, d: date, model: str, cfg: dict, step) -> tuple[list[dict], list[dict]]:
    start, end = window(d)
    built, n_cands, failed = build_cards(conn, d, model, cfg, start, end, cfg["card_candidates"])
    top, ext = rank(built, cfg)
    yt = youtube_search(top + ext, d)
    save_cards(conn, d, top, ext)
    for b in built:
        conn.execute("update event_snapshot set score = %s where event_id = %s and base_date = %s",
                     (b["score"]["top"], b["event_id"], d))
    step("cards", candidates=n_cands, built=len(built), failed=failed, top=len(top), extension=len(ext), **yt)
    return top, ext


def deliver(d: date, top: list[dict], ext: list[dict], send: bool = True) -> dict:
    """텔레그램(짧게) + 메일(카드 전체). 한쪽이 실패해도 다른 쪽은 보낸다."""
    msg = briefing.text(d, top, ext)
    if not send:
        print(msg)
        return {"telegram": False, "email": False, "chars": len(msg)}
    out = {"telegram": telegram.send(msg), "email": False, "chars": len(msg)}
    try:
        out["email"] = mail.send(d, top, ext)
    except Exception as e:                       # 메일 실패가 배치 전체를 실패시키지 않게
        out["email_error"] = type(e).__name__          # 메시지에 주소가 섞일 수 있어 종류만 (공개 로그)
        print(f"email: 실패 {out['email_error']}")
    return out


def refresh_videos(d: date) -> int:
    """이미 만든 카드에 유튜브 검색 결과만 다시 붙인다 (LLM 호출 없음)."""
    with db.connect() as conn:
        rows = conn.execute("select id, body from card where base_date = %s order by kind desc, rank", (d,)).fetchall()
        cards = [r["body"] for r in rows]
        for b in cards:
            b["videos"] = [v for v in b.get("videos") or [] if v.get("via") != "search"]
        out = youtube_search(cards, d)
        for r, b in zip(rows, cards):
            conn.execute("update card set body = %s where id = %s", (json.dumps(b, ensure_ascii=False, default=str), r["id"]))
        conn.commit()
    print(f"refresh-videos {d}: {json.dumps(out, ensure_ascii=False)}")
    for b in cards:
        print(f"\n{b['title']}  [검색어: {b.get('yt_query') or b['title']}]")
        for v in b.get("videos") or []:
            print(f"   {v['channel']} · {v['title']} (조회 {v.get('views')})")
    return 0


def resend(d: date) -> int:
    """이미 만든 카드로 브리핑만 다시 보낸다 (테스트·재발송용)."""
    with db.connect() as conn:
        rows = conn.execute("select kind, body from card where base_date = %s order by kind, rank", (d,)).fetchall()
    top = [r["body"] for r in rows if r["kind"] == "top"]
    ext = [r["body"] for r in rows if r["kind"] == "extension"]
    out = deliver(d, top, ext)
    print(f"resend {d}: top={len(top)} ext={len(ext)} {json.dumps(out, ensure_ascii=False)}")
    return 0 if out["telegram"] or out["email"] else 1


def process(conn, base_date: date, start: datetime, end: datetime, now: datetime, cfg: dict, step) -> str:
    """번역 마무리 → 임베딩·묶기 → 사건 연결 → 변화 감지·저장. [start, end) 기사를 base_date 기준으로 다시 계산한다."""
    # ② 번역 마무리 (매시간 수집에서 못 한 것)
    for _ in range(3):
        t = translate.run(conn, now)
        if t["pending"] == 0 or t["translated"] == 0:
            break
    step("translate", **t)

    reset_day(conn, base_date)
    conn.commit()

    # ③ 임베딩 + 묶기
    articles = load_articles(conn, start, end)
    vecs, model = embed_articles(articles)
    clusters = cl.initial(articles, vecs, cfg["cluster_sim"])
    n_initial = len(clusters)
    merged = cl.merge_borderline(clusters, cfg["merge_low"], cfg["cluster_sim"])
    for c in clusters:
        c.stats = cl.stats(c)
    significant = sorted((c for c in clusters if c.stats["n_sources"] >= cfg["min_sources"]),
                         key=lambda c: (c.stats["n_sources"], c.stats["n_articles"]), reverse=True)
    significant = significant[:cfg["max_events_per_day"]]
    step("cluster", articles=len(articles), model=model, clusters=n_initial, llm_merges=merged,
         significant=len(significant))

    # ④ 사건 연결
    links = ev.link(conn, significant, base_date, model, cfg)
    step("link", auto=sum(l.method == "auto" for l in links), llm=sum(l.method == "llm" for l in links),
         new=sum(l.method == "new" for l in links))

    # ⑤ 변화 감지: 기존 사건은 오늘 묶음을 합쳐 하나로, 새 사건은 묶음마다
    inputs: list[fx.EventInput] = []
    by_event: dict[int, fx.EventInput] = {}
    key_of_cluster: dict[int, str] = {}
    for l in links:
        if l.event_id is not None and l.event_id in by_event:
            by_event[l.event_id].articles += l.cluster.articles
            key_of_cluster[id(l.cluster)] = by_event[l.event_id].key
            continue
        existing, title = [], None
        if l.event_id is not None:
            title = conn.execute("select title from event where id = %s", (l.event_id,)).fetchone()["title"]
            existing = [r["fact"] for r in conn.execute(
                "select fact from event_fact where event_id = %s order by first_seen_date, id", (l.event_id,))]
        item = fx.EventInput(f"E{len(inputs) + 1}", l.event_id, title, existing, list(l.cluster.articles))
        inputs.append(item)
        key_of_cluster[id(l.cluster)] = item.key
        if l.event_id is not None:
            by_event[l.event_id] = item
    fstats = fx.extract(inputs)

    # 저장
    event_of_input: dict[str, int] = {}
    for item in inputs:
        res = item.result
        if not res:
            continue
        if item.event_id is None:
            if not res["facts"]:
                continue                                  # 사실이 없는 새 묶음은 사건으로 만들지 않음
            eid = conn.execute("""
                insert into event (title, first_seen_date, last_change_date, verification)
                values (%s, %s, %s, %s) returning id
            """, (res["title"] or item.articles[0].title[:60], base_date, base_date,
                  res["verification"] or "확인 대기")).fetchone()["id"]
        else:
            eid = item.event_id
            if res["facts"]:
                conn.execute("update event set last_change_date = %s where id = %s", (base_date, eid))
            if res["verification"]:
                conn.execute("update event set verification = %s where id = %s", (res["verification"], eid))
        event_of_input[item.key] = eid
        for f in res["facts"]:
            conn.execute("""
                insert into event_fact (event_id, fact, change_type, first_seen_date, article_ids, needs_review)
                values (%s, %s, %s, %s, %s, %s)
            """, (eid, f["fact"], f["change_type"], base_date, f["article_ids"], f["needs_review"]))
        all_facts = [r["fact"] for r in conn.execute("select fact from event_fact where event_id = %s", (eid,))]
        conn.execute("""insert into event_snapshot (event_id, base_date, facts_hash) values (%s, %s, %s)
                        on conflict (event_id, base_date) do update set facts_hash = excluded.facts_hash""",
                     (eid, base_date, fx.facts_hash(all_facts)))

    # 묶음 저장 (의미 있는 묶음만 — 단발 기사는 저장하지 않음)
    for l in links:
        c = l.cluster
        eid = event_of_input.get(key_of_cluster.get(id(c)))
        cid = conn.execute("""
            insert into cluster (base_date, article_ids, n_articles, n_sources, n_wire, has_intl, has_domestic,
                                 embed_model, event_id, link_method)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
        """, (base_date, [a.id for a in c.articles], c.stats["n_articles"], c.stats["n_sources"],
              c.stats["n_wire"], c.stats["has_intl"], c.stats["has_domestic"], model, eid,
              l.method if eid else None)).fetchone()["id"]
        conn.execute("update article set cluster_id = %s where id = any(%s)", (cid, [a.id for a in c.articles]))
    conn.commit()
    step("facts", events_in=len(inputs), events_saved=len(event_of_input), **fstats)
    return model


def run(base_date: date | None = None, send: bool = True) -> int:
    now = datetime.now(timezone.utc)
    base_date = base_date or now.astimezone(KST).date()
    cfg = config.ops()["pipeline"]
    start, end = window(base_date)
    detail: dict = {"base_date": base_date.isoformat(), "steps": {}}
    t0 = _time.monotonic()

    def step(name, **info):
        detail["steps"][name] = {**info, "t": round(_time.monotonic() - t0, 1)}
        print(f"daily {name}: {json.dumps(info, ensure_ascii=False)}")

    with db.connect() as conn:
        log_id = conn.execute("insert into run_log (job, step) values ('daily', 'start') returning id").fetchone()["id"]
        conn.commit()
        try:
            model = process(conn, base_date, start, end, now, cfg, step)

            # ⑦ 점수화 → ⑧ 카드
            top, ext = make_cards(conn, base_date, model, cfg, step)
            conn.commit()

            step("briefing", **deliver(base_date, top, ext, send))

            detail["llm"] = {"calls": llm.usage.calls, "fallbacks": llm.usage.fallbacks,
                             "waits_s": round(llm.usage.waits_s, 1)}
            conn.execute("update run_log set finished_at = now(), ok = true, step = 'briefing', detail = %s where id = %s",
                         (json.dumps(detail, ensure_ascii=False), log_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            detail["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            conn.execute("update run_log set finished_at = now(), ok = false, detail = %s where id = %s",
                         (json.dumps(detail, ensure_ascii=False), log_id))
            conn.commit()
            if send:
                telegram.send(f"⚠️ 아침 배치 실패 ({base_date})\n{detail['error']}", alert=True)
            raise
    print(f"daily done in {_time.monotonic() - t0:.0f}s llm={llm.usage.calls}")
    return 0
