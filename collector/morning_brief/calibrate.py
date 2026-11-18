"""임계값 보정용: 기준일 기사들을 임베딩해 가까운 기사 쌍을 유사도 구간별로 출력한다."""
from datetime import date

import numpy as np

from . import db, llm
from .daily import load_articles, window


def run(d: date) -> int:
    with db.connect() as conn:
        arts = load_articles(conn, *window(d))
    vecs, model = llm.embed([f"{a.title}. {a.summary or ''}"[:500] for a in arts])
    S = vecs @ vecs.T
    np.fill_diagonal(S, -1)
    print(f"model={model} articles={len(arts)}")
    pairs = [(S[i, j], i, j) for i in range(len(arts)) for j in range(i + 1, len(arts))
             if arts[i].source_id != arts[j].source_id and S[i, j] >= 0.45]
    pairs.sort(reverse=True)
    bins = {}
    for s, i, j in pairs:
        b = f"{int(s * 20) / 20:.2f}"
        bins.setdefault(b, []).append((s, i, j))
    for b in sorted(bins, reverse=True):
        items = bins[b]
        print(f"\n--- {b}~ ({len(items)}쌍)")
        for s, i, j in items[:8]:
            print(f"  {s:.3f} | {arts[i].title[:45]} || {arts[j].title[:45]}")
    return 0
