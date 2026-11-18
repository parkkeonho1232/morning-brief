"""⑧ 카드 생성. LLM은 해석·질문만 쓰고, '새로 확인된 사실'은 검증된 event_fact 중에서 고르게만 한다."""
import json
from datetime import date

from .. import llm
from .score import Candidate

MAX_ARTICLES = 30

PROMPT = """너는 시사 방송 편집회의 준비 담당이다. 아래 사건 하나로 제작진용 아이템 카드를 만든다.

절대 규칙:
1. 주어진 정보(사실 목록·기사 제목/요약·일정)만 근거로 쓴다. 바깥 지식·추측 금지.
2. 확인 상태가 '보도된 의혹'이면 어떤 문장에서도 단정하지 말 것 ("~했다" 대신 "~라는 의혹").
3. 공인이 아닌 일반인의 실명은 쓰지 않는다 ("A씨").
4. 매체별 관점(perspectives)은 주어진 그룹 이름만 쓰고, 그 그룹 기사 제목·요약에서 드러난 강조점만 적는다.
   '진보·보수·친여·친야' 같은 성향 표현은 쓰지 말 것. 기사가 없는 그룹은 넣지 않는다.
5. new_fact_ids는 '오늘의 사실' 목록의 id 중 가장 중요한 것 최대 3개. 새 문장을 지어내지 말 것.
6. people: 오늘 기사 제목·요약에 **이름이 실제로 나온** 인물 중 방송 섭외·언급 후보가 될 만한 사람 최대 5명
   (당사자, 발언한 정치인·공직자, 인용된 전문가, 기업 대표, 유튜버 등). 이름은 기사에 쓰인 그대로,
   article_ids는 그 이름이 나온 기사 id. 일반인(피의자·피해자·제보자 등 공인이 아닌 사람)은 넣지 않는다.
6-2. ai_suggestions: 기사에는 없지만 이 사건을 다루기에 잘 맞는 실존 공인 최대 3명 (정치인, 학자, 언론인,
   시사 유튜버·방송인 등). 확실히 아는 사람만, 현재 직함을 모르면 role에 분야만 쓴다. 애매하면 빈 목록.
   people과 겹치지 않게.
6-3. people에 기사를 쓴 기자·특파원·앵커는 넣지 않는다 (보도한 사람이지 사건의 인물이 아님).
7. importance는 '오늘 꼭 알아야 할 뉴스'로서의 중요도 0~1 (사회적 파급·공적 관심 기준. 스포츠·사고는 낮게).

출력 JSON:
{{"why_now": "오늘 관심이 커진 구체적 계기 1~2문장",
  "importance": 0.0,
  "new_fact_ids": [1, 2],
  "perspectives": [{{"group": "그룹명", "emphasis": "강조점 1줄"}}],
  "core_conflict": ["부딪히는 가치 1", "가치 2"],
  "questions": {{"opening": "도입 질문", "followups": ["확장 질문1", "확장 질문2", "확장 질문3"]}},
  "prepare": {{"expert_fields": ["분야"], "visuals": ["자료화면"], "checks": ["추가 확인 사항"]}},
  "people": [{{"name": "기사 속 이름", "role": "직함·관계", "why": "섭외·언급 이유 1줄", "article_ids": [1]}}],
  "ai_suggestions": [{{"name": "이름", "role": "직함 또는 분야", "why": "추천 이유 1줄"}}],
  "yt_query": "이 사건을 다룬 유튜브 영상을 찾을 한국어 검색어 (핵심 인물·대상 + 쟁점, 2~4단어)"}}

사건:
{event}
"""


def _articles(conn, ids: list[int]) -> list[dict]:
    rows = conn.execute("""
        select a.id, s.name as source, coalesce(s.grp, '기타') as grp, s.region, s.paywall, a.via, a.url,
               coalesce(a.title_ko, a.title) as title, coalesce(a.summary_ko, a.summary) as summary, a.published_at
        from article a join source s on s.id = a.source_id where a.id = any(%s) order by a.published_at
    """, (ids,)).fetchall()
    # 그룹·매체 다양성 우선
    seen, first, rest = set(), [], []
    for r in rows:
        (rest if r["source"] in seen else first).append(r)
        seen.add(r["source"])
    return (first + rest)[:MAX_ARTICLES]


def _timeline(conn, event_id: int) -> list[dict]:
    return [dict(r) | {"date": r["first_seen_date"].isoformat()} for r in conn.execute("""
        select id, fact, change_type, first_seen_date, needs_review, article_ids from event_fact
        where event_id = %s order by first_seen_date, id""", (event_id,))]


REPORTER = ("기자", "특파원", "앵커", "논설위원", "통신원")
PRIVATE = ("A씨", "B씨", "C씨", "씨(", "남성", "여성", "피의자", "피해자", "학생", "주민", "직원")


def _people(raw_people, arts: list[dict]) -> list[dict]:
    """기사 속 인물: 이름이 근거 기사 제목·요약에 실제로 있어야 통과."""
    text = {a["id"]: f"{a['title']} {a.get('summary') or ''}" for a in arts}
    out, seen = [], set()
    for p in raw_people or []:
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        ids = [i for i in (p.get("article_ids") or []) if isinstance(i, int) and i in text and name and name in text[i]]
        if not name or len(name) > 20 or not ids or name in seen or any(k in name for k in PRIVATE):
            continue
        role = (p.get("role") or "").strip()
        if any(k in role for k in REPORTER):
            continue
        seen.add(name)
        out.append({"name": name, "role": role[:40] or None,
                    "why": (p.get("why") or "").strip()[:120] or None, "article_ids": sorted(set(ids))})
    return out[:5]


def _ai(raw_ai, exclude: set[str]) -> list[dict]:
    out = []
    for p in raw_ai or []:
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        if not name or len(name) > 20 or name in exclude or any(k in name for k in PRIVATE):
            continue
        exclude.add(name)
        out.append({"name": name, "role": (p.get("role") or "").strip()[:40] or None,
                    "why": (p.get("why") or "").strip()[:120] or None})
    return out[:3]


def validate(raw: dict, today_fact_ids: list[int], groups: set[str], arts: list[dict] | None = None) -> dict:
    def s(x, n=300):
        return x.strip()[:n] if isinstance(x, str) and x.strip() else None

    fact_ids = [i for i in (raw.get("new_fact_ids") or []) if i in today_fact_ids][:3] or today_fact_ids[:3]
    q = raw.get("questions") or {}
    prep = raw.get("prepare") or {}

    def num(x):
        try:
            return max(0.0, min(1.0, float(x)))
        except (TypeError, ValueError):
            return 0.0
    return {
        "why_now": s(raw.get("why_now")),
        "importance": num(raw.get("importance")),
        "new_fact_ids": fact_ids,
        "perspectives": [{"group": p["group"], "emphasis": s(p.get("emphasis"), 160)}
                         for p in raw.get("perspectives") or []
                         if isinstance(p, dict) and p.get("group") in groups and s(p.get("emphasis"))],
        "core_conflict": [s(x, 80) for x in (raw.get("core_conflict") or []) if s(x)][:2],
        "questions": {"opening": s(q.get("opening")),
                      "followups": [s(x) for x in (q.get("followups") or []) if s(x)][:3]},
        "prepare": {"expert_fields": [s(x, 40) for x in prep.get("expert_fields") or [] if s(x)][:4],
                    "visuals": [s(x, 80) for x in prep.get("visuals") or [] if s(x)][:4],
                    "checks": [s(x, 120) for x in prep.get("checks") or [] if s(x)][:4]},
        "yt_query": s(raw.get("yt_query"), 40),
        "people": (people := _people(raw.get("people"), arts or [])),
        "ai_suggestions": _ai(raw.get("ai_suggestions"), {p["name"] for p in people}),
    }


def build(conn, c: Candidate, d: date) -> dict | None:
    arts = _articles(conn, c.article_ids)
    timeline = _timeline(conn, c.event_id)
    today_ids = [f["id"] for f in c.facts_today]
    groups = {a["grp"] for a in arts}
    event = {
        "title": c.title, "verification": c.verification, "first_seen": c.first_seen_date.isoformat(),
        "signals": c.signals,
        "earlier_facts": [{"date": f["date"], "type": f["change_type"], "fact": f["fact"]}
                          for f in timeline if f["first_seen_date"] < d][-10:],
        "today_facts": [{"id": f["id"], "type": f["change_type"], "fact": f["fact"]} for f in c.facts_today],
        "today_articles": [{"id": a["id"], "group": a["grp"], "source": a["source"], "title": a["title"],
                            "summary": (a["summary"] or "")[:200]} for a in arts],
        "schedules_7d": c.schedules,
    }
    raw = llm.generate_json(PROMPT.format(event=json.dumps(event, ensure_ascii=False, default=str)), tier="main")
    v = validate(raw if isinstance(raw, dict) else {}, today_ids, groups, arts)

    # 출처는 코드가 근거 article_id에서 만든다 (LLM이 링크를 만들지 않음)
    cited = sorted({i for f in c.facts_today if f["id"] in v["new_fact_ids"] for i in f["article_ids"]})
    src = {r["id"]: r for r in conn.execute("""
        select a.id, s.name as source, s.paywall, a.via, a.url, coalesce(a.title_ko, a.title) as title
        from article a join source s on s.id = a.source_id where a.id = any(%s)""", (cited,))}
    facts = [{"id": f["id"], "fact": f["fact"], "change_type": f["change_type"], "needs_review": f["needs_review"],
              "sources": [{"source": src[i]["source"], "url": src[i]["url"], "title": src[i]["title"],
                           "paywall": src[i]["paywall"], "via": src[i]["via"]} for i in f["article_ids"] if i in src]}
             for f in c.facts_today if f["id"] in v["new_fact_ids"]]
    if not facts:
        return None                     # 근거 있는 사실이 없으면 카드로 노출하지 않음
    return {
        "event_id": c.event_id, "title": c.title, "verification": c.verification, "why_now": v["why_now"],
        "new_facts": facts, "signals": c.signals, "perspectives": v["perspectives"],
        "core_conflict": v["core_conflict"], "questions": v["questions"],
        "prepare": v["prepare"], "schedules": c.schedules,
        "people": [{**p, "sources": [{"source": a["source"], "url": a["url"]} for a in arts if a["id"] in p["article_ids"]][:2]}
                   for p in v["people"]],
        "ai_suggestions": v["ai_suggestions"], "videos": c.videos, "yt_query": v["yt_query"],
        "timeline": [{"date": f["date"], "change_type": f["change_type"], "fact": f["fact"]} for f in timeline],
        "score": {"base": c.base_score, "importance": v["importance"]},
    }
