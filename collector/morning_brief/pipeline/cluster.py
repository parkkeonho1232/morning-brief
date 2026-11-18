"""③ 기사 묶기: 임베딩 평균연결 군집 → 경계가 애매한 묶음 쌍만 LLM이 '같은 사건인가' 판정."""
import json
from dataclasses import dataclass, field

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

from .. import llm


@dataclass
class Article:
    id: int
    source_id: int
    source: str
    grp: str | None
    region: str
    title: str             # 한국어 (해외 기사는 번역본)
    summary: str | None
    published_at: object


@dataclass
class Cluster:
    articles: list[Article]
    centroid: np.ndarray
    merged_by_llm: bool = False
    stats: dict = field(default_factory=dict)

    def titles(self, n: int = 3) -> list[str]:
        seen, out = set(), []
        for a in self.articles:
            if a.title not in seen:
                seen.add(a.title)
                out.append(a.title)
            if len(out) == n:
                break
        return out


def _centroid(vecs: np.ndarray) -> np.ndarray:
    c = vecs.mean(axis=0)
    return c / (np.linalg.norm(c) or 1)


def initial(articles: list[Article], vecs: np.ndarray, sim: float) -> list[Cluster]:
    """평균연결(average linkage): 묶음 안 기사들의 평균 유사도가 sim 이상일 때만 합친다 (사슬처럼 번지는 것 방지)."""
    if len(articles) == 0:
        return []
    if len(articles) == 1:
        return [Cluster(articles, vecs[0])]
    labels = fcluster(linkage(vecs, method="average", metric="cosine"), t=1 - sim, criterion="distance")
    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)
    return [Cluster([articles[i] for i in idx], _centroid(vecs[idx])) for idx in groups.values()]


JUDGE_PROMPT = """너는 뉴스 편집자다. 아래 각 쌍(A, B)의 기사 묶음이 '같은 사건'을 다루는지 판정하라.
같은 사건: 동일한 사건·발표·논란의 후속·반응·해명 포함. 다른 사건: 주제만 비슷하고 당사자나 계기가 다름.

출력: {{"items": [{{"pair": 0, "same": true}}]}}

{pairs}
"""


def merge_borderline(clusters: list[Cluster], low: float, high: float, max_pairs: int = 80) -> int:
    """중심 유사도가 [low, high)인 묶음 쌍을 LLM에 물어 합친다. 반환: 합친 횟수."""
    idx = [i for i, c in enumerate(clusters) if len(c.articles) >= 2]
    if len(idx) < 2:
        return 0
    C = np.stack([clusters[i].centroid for i in idx])
    S = C @ C.T
    pairs = [(S[a, b], idx[a], idx[b]) for a in range(len(idx)) for b in range(a + 1, len(idx))
             if low <= S[a, b] < high]
    pairs = sorted(pairs, reverse=True)[:max_pairs]
    if not pairs:
        return 0
    same = []
    for start in range(0, len(pairs), 40):
        chunk = pairs[start:start + 40]
        text = "\n".join(json.dumps({"pair": start + k, "A": clusters[i].titles(), "B": clusters[j].titles()},
                                    ensure_ascii=False) for k, (_, i, j) in enumerate(chunk))
        result = llm.generate_json(JUDGE_PROMPT.format(pairs=text), tier="lite")
        for it in result.get("items", []) if isinstance(result, dict) else []:
            p = it.get("pair")
            if it.get("same") is True and isinstance(p, int) and 0 <= p < len(pairs):
                same.append(pairs[p])
    # union-find로 합치기
    parent = list(range(len(clusters)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for _, i, j in same:
        parent[find(i)] = find(j)
    merged: dict[int, Cluster] = {}
    for i, c in enumerate(clusters):
        root = find(i)
        if root in merged:
            m = merged[root]
            n1, n2 = len(m.articles), len(c.articles)
            m.articles += c.articles
            m.centroid = (m.centroid * n1 + c.centroid * n2)
            m.centroid /= np.linalg.norm(m.centroid) or 1
            m.merged_by_llm = True
        else:
            merged[root] = c
    clusters[:] = list(merged.values())
    return len(same)


def stats(c: Cluster) -> dict:
    sources = {a.source_id for a in c.articles}
    return {
        "n_articles": len(c.articles),
        "n_sources": len(sources),
        "n_wire": sum(1 for a in c.articles if a.grp == "통신사"),
        "has_intl": any(a.region == "international" for a in c.articles),
        "has_domestic": any(a.region == "domestic" for a in c.articles),
    }
