"""④ 사건 연결: 오늘 묶음 ↔ 진행 중인 사건. 사건 벡터는 그날 쓴 임베딩 모델로 매번 다시 만든다(모델 혼용 방지)."""
import json
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from .. import llm
from .cluster import Cluster


@dataclass
class Link:
    cluster: Cluster
    event_id: int | None      # None이면 새 사건
    method: str               # new | auto | llm


def active_events(conn, base_date: date, days: int) -> list[dict]:
    rows = conn.execute("""
        select e.id, e.title,
               coalesce((select string_agg(f.fact, ' / ' order by f.first_seen_date desc, f.id desc)
                         from (select fact, first_seen_date, id from event_fact where event_id = e.id
                               order by first_seen_date desc, id desc limit 3) f), '') as recent_facts
        from event e
        where e.status = 'active' and coalesce(e.last_change_date, e.first_seen_date) >= %s
          and e.first_seen_date < %s
    """, (base_date - timedelta(days=days), base_date)).fetchall()
    return rows


LINK_PROMPT = """너는 뉴스 편집자다. 오늘 기사 묶음(C)이 진행 중인 사건(E)의 '후속'인지 판정하라.
같은 사건: 같은 당사자·같은 논란·같은 정책의 후속 보도, 해명, 반박, 조치. 주제만 비슷하면 다른 사건.

출력: {{"items": [{{"pair": 0, "same": true}}]}}

{pairs}
"""


def link(conn, clusters: list[Cluster], base_date: date, model: str, cfg: dict) -> list[Link]:
    events = active_events(conn, base_date, cfg["event_active_days"])
    if not events:
        return [Link(c, None, "new") for c in clusters]
    texts = [f"{e['title']}. {e['recent_facts']}"[:600] for e in events]
    E, _ = llm.embed(texts, force_model=model)
    C = np.stack([c.centroid for c in clusters])
    S = C @ E.T
    links, ask = [], []
    for i, c in enumerate(clusters):
        j = int(S[i].argmax())
        s = float(S[i, j])
        if s >= cfg["link_high"]:
            links.append(Link(c, events[j]["id"], "auto"))
        elif s >= cfg["link_low"]:
            links.append(Link(c, None, "new"))
            ask.append((len(links) - 1, j))
        else:
            links.append(Link(c, None, "new"))
    for start in range(0, len(ask), 40):
        chunk = ask[start:start + 40]
        text = "\n".join(json.dumps({"pair": k, "C": links[li].cluster.titles(),
                                     "E": {"title": events[ej]["title"], "facts": events[ej]["recent_facts"][:300]}},
                                    ensure_ascii=False) for k, (li, ej) in enumerate(chunk))
        result = llm.generate_json(LINK_PROMPT.format(pairs=text), tier="lite")
        for it in result.get("items", []) if isinstance(result, dict) else []:
            p = it.get("pair")
            if it.get("same") is True and isinstance(p, int) and 0 <= p < len(chunk):
                li, ej = chunk[p]
                links[li].event_id, links[li].method = events[ej]["id"], "llm"
    return links
