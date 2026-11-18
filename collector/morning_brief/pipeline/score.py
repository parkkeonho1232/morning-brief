"""⑦ 점수화: 오늘 변화가 있는 사건의 기본 점수. 중요도는 카드 생성 후 더해진다(cards.py).

신호: 보도 확산(독립 매체 수·증가), 변화 강도, 국내외 동시성, 7일 내 공식 일정.
유튜브 반응은 채널 기준선이 쌓인 뒤(Phase 2) 추가한다.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np

from .. import llm
from .normalize import KST

CHANGE_WEIGHT = {"인정": 3.0, "반박 자료": 3.0, "공식 조치": 2.0, "확장": 1.5, "수치 변경": 1.5,
                 "당사자 해명": 1.2, "최초 보도": 1.0}


@dataclass
class Candidate:
    event_id: int
    title: str
    verification: str
    first_seen_date: date
    n_sources: int
    n_sources_prev: int
    has_intl: bool
    has_domestic: bool
    article_ids: list[int]
    facts_today: list[dict]
    schedules: list[dict] = field(default_factory=list)
    videos: list[dict] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    base_score: float = 0.0


def candidates(conn, d: date) -> list[Candidate]:
    rows = conn.execute("""
        select e.id, e.title, e.verification, e.first_seen_date,
               coalesce(max(c.n_sources), 0) as n_sources, bool_or(c.has_intl) as has_intl,
               bool_or(c.has_domestic) as has_domestic,
               array_agg(distinct a_id) as article_ids,
               (select coalesce(max(p.n_sources), 0) from cluster p
                 where p.event_id = e.id and p.base_date = %s) as n_sources_prev
        from event e
        join cluster c on c.event_id = e.id and c.base_date = %s
        cross join lateral unnest(c.article_ids) as a_id
        where e.last_change_date = %s
        group by e.id
    """, (d - timedelta(days=1), d, d)).fetchall()
    out = []
    for r in rows:
        facts = conn.execute("""select id, fact, change_type, article_ids, needs_review from event_fact
                                where event_id = %s and first_seen_date = %s order by id""", (r["id"], d)).fetchall()
        out.append(Candidate(r["id"], r["title"], r["verification"], r["first_seen_date"], r["n_sources"],
                             r["n_sources_prev"], bool(r["has_intl"]), bool(r["has_domestic"]),
                             list(r["article_ids"]), [dict(f) for f in facts]))
    return out


def attach_schedules(conn, cands: list[Candidate], d: date, model: str, sim: float = 0.55):
    """7일 내 공식 일정 중 사건과 의미가 가까운 것을 붙인다 (임베딩은 그날 모델로)."""
    start = datetime.combine(d, time(0, 0), KST)
    rows = conn.execute("""select org, title, starts_at, all_day, kind, place from schedule
                           where starts_at >= %s and starts_at < %s order by starts_at""",
                        (start, start + timedelta(days=7))).fetchall()
    if not rows or not cands:
        return
    S_vec, _ = llm.embed([f"{r['org']} {r['title']}" for r in rows], force_model=model)
    E_vec, _ = llm.embed([c.title + ". " + " ".join(f["fact"] for f in c.facts_today[:3]) for c in cands],
                         force_model=model)
    sims = E_vec @ S_vec.T
    for i, c in enumerate(cands):
        for j in np.argsort(-sims[i])[:3]:
            if sims[i, j] >= sim:
                r = rows[j]
                c.schedules.append({"org": r["org"], "title": r["title"], "kind": r["kind"],
                                    "starts_at": r["starts_at"].astimezone(KST).strftime("%m-%d %H:%M"),
                                    "all_day": r["all_day"], "sim": round(float(sims[i, j]), 2)})


def attach_videos(conn, cands: list[Candidate], start: datetime, end: datetime, model: str, sim: float = 0.6):
    """기준 창 안에 올라온 시사 유튜브 영상 중 사건과 뜻이 가까운 것 (섭외·패널 후보 참고용).

    영상 제목만 쓰고, 링크·조회수는 코드가 붙인다.
    """
    rows = conn.execute("""
        select v.id, v.title, v.published_at, c.name as channel,
               (select s.views from yt_stat s where s.video_id = v.id order by s.captured_at desc limit 1) as views
        from yt_video v join yt_channel c on c.id = v.channel_id
        where c.kind = 'sisa' and v.published_at >= %s and v.published_at < %s
    """, (start - timedelta(hours=12), end)).fetchall()
    if not rows or not cands:
        return
    V_vec, _ = llm.embed([r["title"] for r in rows], force_model=model)
    E_vec, _ = llm.embed([c.title + ". " + " ".join(f["fact"] for f in c.facts_today[:3]) for c in cands],
                         force_model=model)
    sims = E_vec @ V_vec.T
    for i, c in enumerate(cands):
        for j in np.argsort(-sims[i])[:3]:
            if sims[i, j] >= sim:
                r = rows[j]
                c.videos.append({"channel": r["channel"], "title": r["title"],
                                 "url": f"https://www.youtube.com/watch?v={r['id']}",
                                 "views": r["views"], "sim": round(float(sims[i, j]), 2)})


def base_scores(cands: list[Candidate], d: date):
    for c in cands:
        growth = max(c.n_sources - c.n_sources_prev, 0)
        change = sum(CHANGE_WEIGHT.get(f["change_type"], 1.0) for f in c.facts_today[:5])
        both = c.has_intl and c.has_domestic
        c.signals = {"sources": c.n_sources, "sources_growth": growth, "change_strength": round(change, 1),
                     "intl_and_domestic": both, "schedules_7d": len(c.schedules), "new_event": c.first_seen_date == d}
        c.base_score = round(np.log1p(c.n_sources) * 2.0 + np.log1p(growth) + change + (1.5 if both else 0)
                             + (1.0 if c.schedules else 0), 2)
