"""② 번역: 해외 기사 제목·요약 → 한국어. 원문은 그대로 두고 title_ko/summary_ko에 저장한다."""
import json
from datetime import timedelta

from .. import llm

BATCH = 40
MAX_PER_RUN = 160        # 한 번 수집 때 번역할 최대 건수 (무료 등급 보호)

PROMPT = """너는 한국 시사 방송 제작진을 위한 외신 번역가다. 아래 해외 기사들의 제목과 요약을 한국어로 번역하라.

규칙:
- 원문에 없는 내용을 더하거나 해석하지 말 것. 주장·의혹은 원문의 단정 수준을 그대로 유지할 것.
- 인명·지명·기관명은 국내 언론이 쓰는 표기로 (예: Donald Trump → 트럼프, Kyiv → 키이우).
- 제목은 한국 신문 제목처럼 간결하게. 요약이 없으면 summary_ko는 null.
- 입력의 id를 그대로 돌려줄 것.

출력 형식: {{"items": [{{"id": 123, "title_ko": "...", "summary_ko": "... 또는 null"}}]}}

입력:
{articles}
"""


def run(conn, now) -> dict:
    rows = conn.execute("""
        select a.id, a.title, a.summary from article a
        where a.lang <> 'ko' and a.title_ko is null and a.collected_at > %s
        order by a.published_at desc limit %s
    """, (now - timedelta(hours=48), MAX_PER_RUN)).fetchall()
    done = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        payload = json.dumps([{"id": r["id"], "title": r["title"], "summary": r["summary"]} for r in batch],
                             ensure_ascii=False)
        result = llm.generate_json(PROMPT.format(articles=payload), tier="lite")
        ids = {r["id"] for r in batch}
        for it in (result.get("items") if isinstance(result, dict) else result) or []:
            if it.get("id") in ids and it.get("title_ko"):
                conn.execute("update article set title_ko = %s, summary_ko = %s where id = %s",
                             (it["title_ko"].strip(), (it.get("summary_ko") or None), it["id"]))
                done += 1
        conn.commit()
    return {"pending": len(rows), "translated": done}
