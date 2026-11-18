"""⑤ 변화 감지: 사건별로 '기존 사실 목록'과 오늘 기사를 주고 새로 확인된 사실만 받는다.

가드레일(CLAUDE.md): 모든 사실은 근거 article_id ≥ 1 (주어진 목록 안에서만), 의혹은 단정 금지.
LLM 출력은 코드에서 다시 검증하고, 조건을 못 맞춘 사실은 버린다.
"""
import hashlib
import json
from dataclasses import dataclass, field

from .. import llm
from .cluster import Article

CHANGE_TYPES = ("최초 보도", "당사자 해명", "인정", "반박 자료", "공식 조치", "확장", "수치 변경")
VERIFICATION = ("공식 확인", "보도된 의혹", "당사자 반박", "확인 대기")
HIGH_RISK = ("인정", "반박 자료")
MAX_ARTICLES = 25
MAX_FACT_LEN = 220


@dataclass
class EventInput:
    key: str                       # 프롬프트 안 식별자 (E1, E2 …)
    event_id: int | None           # None이면 새 사건
    title: str | None
    existing_facts: list[str]
    articles: list[Article]
    result: dict = field(default_factory=dict)


PROMPT = """너는 시사 방송 편집회의용 팩트 정리 담당이다. 각 사건(E)마다 '기존 사실'과 '오늘 기사'(제목·요약)를 준다.
오늘 기사에서 기존 사실과 비교해 **새로 확인된 사실**만 뽑아라.

규칙 (반드시 지킬 것):
1. 주어진 제목·요약에 있는 내용만 쓴다. 바깥 지식, 추측, 평가 금지.
2. 각 사실에 근거 기사 번호(article_ids)를 1개 이상 붙인다. 오늘 기사 목록에 있는 번호만 쓸 수 있다.
3. 기존 사실과 같은 내용(표현만 다른 것 포함)은 빼라. 새로운 게 없으면 빈 목록.
4. 의혹·주장은 단정하지 말 것. "~했다" 대신 "OO 보도에 따르면 ~라는 의혹이 제기됨" 형식.
   한 매체만 보도한 주장은 "OO 보도에 따르면"으로 시작.
5. 당사자 해명·반박이 있으면 별도 사실(change_type "당사자 해명")로 남긴다.
6. change_type은 다음 중 하나: {types}
   - 최초 보도: 새 사건의 첫 보도 내용 / 인정: 당사자가 처음 인정 / 반박 자료: 기존 설명을 뒤집는 자료
   - 공식 조치: 조사 착수·압수수색·발표 등 / 확장: 피해·쟁점 범위 확대 / 수치 변경: 숫자가 바뀜
7. 사실 문장은 한 문장, {maxlen}자 이내, 중립적 표현.
   공인(정치인·고위공직자·기업 대표·유명인)이 아닌 일반인은 기사에 실명이 있어도 실명을 쓰지 말고 "A씨", "20대 남성"처럼 쓴다.
8. verification(사건 전체의 확인 상태): {verif} 중 하나.
   - 보도된 의혹: 비리·위법·부당행위·스캔들 같은 '의혹'이 보도됐지만 당국·당사자 확인이 없을 때만.
   - 당사자 반박: 그 의혹을 당사자가 부인·반박 중일 때.
   - 공식 확인: 당국·기관·당사자의 발표나 공식 기록이 있는 일 (사고·경기 결과·정책 발표·판결·수사 착수 등).
   - 확인 대기: 위 어느 것도 판단하기 어려울 때.
   의혹이 아닌 일반 사건(사고, 발표, 경기, 기업 공시 등)에는 '보도된 의혹'을 쓰지 말 것.
9. 새 사건(title이 null)이면 title에 중립적인 사건명(20자 안팎, 인물·기관 + 쟁점)을 지어라. 기존 사건이면 null.
   사건명에도 일반인 실명은 넣지 않는다.
   여러 사실이 섞인 잡다한 묶음이면 가장 큰 사건 하나만 다뤄라.

출력: {{"events": [{{"key": "E1", "title": "… 또는 null", "verification": "…",
  "new_facts": [{{"fact": "…", "change_type": "…", "article_ids": [12, 34]}}]}}]}}

입력:
{events}
"""


def _pick_articles(articles: list[Article]) -> list[Article]:
    """매체 다양성 우선: 매체별 1건씩 먼저, 요약 있는 기사 우선."""
    ordered = sorted(articles, key=lambda a: (a.summary is None, a.published_at))
    first, rest, seen = [], [], set()
    for a in ordered:
        (rest if a.source_id in seen else first).append(a)
        seen.add(a.source_id)
    return (first + rest)[:MAX_ARTICLES]


def _payload(ev: EventInput) -> dict:
    return {
        "key": ev.key,
        "title": ev.title,
        "existing_facts": ev.existing_facts[-15:],
        "today_articles": [{"id": a.id, "source": a.source, "published": a.published_at.strftime("%m-%d %H:%M"),
                            "title": a.title, "summary": (a.summary or "")[:300]}
                           for a in _pick_articles(ev.articles)],
    }


def validate(ev: EventInput, raw: dict) -> dict:
    """LLM 결과 검증. 통과한 것만 남긴다."""
    allowed = {a.id for a in _pick_articles(ev.articles)}
    existing = {f.strip() for f in ev.existing_facts}
    facts, dropped = [], 0
    for f in raw.get("new_facts") or []:
        text = (f.get("fact") or "").strip()
        ids = [i for i in (f.get("article_ids") or []) if isinstance(i, int) and i in allowed]
        ctype = f.get("change_type")
        if not text or len(text) > MAX_FACT_LEN * 1.3 or not ids or ctype not in CHANGE_TYPES or text in existing:
            dropped += 1
            continue
        facts.append({"fact": text, "change_type": ctype, "article_ids": sorted(set(ids)),
                      "needs_review": ctype in HIGH_RISK})
    verif = raw.get("verification") if raw.get("verification") in VERIFICATION else None
    title = (raw.get("title") or "").strip() or None
    return {"facts": facts, "verification": verif, "title": title if ev.event_id is None else None,
            "dropped": dropped}


def extract(events: list[EventInput], per_call: int = 3) -> dict:
    stats = {"calls": 0, "facts": 0, "dropped": 0, "failed": 0}
    for i in range(0, len(events), per_call):
        chunk = events[i:i + per_call]
        prompt = PROMPT.format(types=", ".join(CHANGE_TYPES), verif=", ".join(VERIFICATION), maxlen=MAX_FACT_LEN,
                               events=json.dumps([_payload(e) for e in chunk], ensure_ascii=False))
        try:
            result = llm.generate_json(prompt, tier="main")
            stats["calls"] += 1
        except llm.LLMError as e:
            stats["failed"] += len(chunk)
            print(f"facts: 실패 {[e.key for e in chunk]} {str(e)[:150]}")
            continue
        by_key = {r.get("key"): r for r in (result.get("events") or [])} if isinstance(result, dict) else {}
        for ev in chunk:
            ev.result = validate(ev, by_key.get(ev.key) or {})
            stats["facts"] += len(ev.result["facts"])
            stats["dropped"] += ev.result["dropped"]
    return stats


def facts_hash(facts: list[str]) -> str:
    return hashlib.sha1("\n".join(sorted(facts)).encode()).hexdigest()[:16]
