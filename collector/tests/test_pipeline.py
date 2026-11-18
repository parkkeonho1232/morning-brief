from datetime import datetime, timezone

import numpy as np

from morning_brief.pipeline import cluster as cl
from morning_brief.pipeline import facts as fx


def art(i, source_id=1, title="t", summary=None, region="domestic", grp=None):
    return cl.Article(i, source_id, f"S{source_id}", grp, region, title, summary,
                      datetime(2026, 11, 15, i % 24, tzinfo=timezone.utc))


def unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_initial_clusters_by_similarity():
    arts = [art(1), art(2, 2), art(3, 3)]
    vecs = np.stack([unit(1, 0, 0), unit(0.98, 0.2, 0), unit(0, 0, 1)])
    clusters = cl.initial(arts, vecs, 0.82)
    sizes = sorted(len(c.articles) for c in clusters)
    assert sizes == [1, 2]


def test_stats_counts_independent_sources_and_wire():
    c = cl.Cluster([art(1, 1, grp="통신사"), art(2, 1, grp="통신사"), art(3, 2, region="international")],
                   unit(1, 0))
    s = cl.stats(c)
    assert s == {"n_articles": 3, "n_sources": 2, "n_wire": 2, "has_intl": True, "has_domestic": True}


def test_merge_borderline_uses_llm_verdict(monkeypatch):
    a = cl.Cluster([art(1), art(2, 2)], unit(1, 0, 0))
    b = cl.Cluster([art(3, 3), art(4, 4)], unit(0.78, 0.6257, 0))      # 유사도 ≈ 0.78 (경계 구간)
    c = cl.Cluster([art(5, 5), art(6, 6)], unit(0, 0, 1))
    monkeypatch.setattr(cl.llm, "generate_json", lambda *a, **k: {"items": [{"pair": 0, "same": True}]})
    clusters = [a, b, c]
    assert cl.merge_borderline(clusters, 0.74, 0.82) == 1
    assert sorted(len(x.articles) for x in clusters) == [2, 4]


def test_validate_drops_facts_without_valid_evidence():
    ev = fx.EventInput("E1", None, None, ["기존 사실"], [art(10, 1, summary="요약"), art(11, 2)])
    raw = {"title": "OO기업 대표 의혹", "verification": "보도된 의혹", "new_facts": [
        {"fact": "OO 보도에 따르면 대표가 자금을 유용했다는 의혹이 제기됨", "change_type": "최초 보도", "article_ids": [10]},
        {"fact": "근거 없는 문장", "change_type": "최초 보도", "article_ids": []},
        {"fact": "목록 밖 근거", "change_type": "확장", "article_ids": [999]},
        {"fact": "잘못된 유형", "change_type": "추측", "article_ids": [11]},
        {"fact": "기존 사실", "change_type": "확장", "article_ids": [11]},
        {"fact": "대표 측이 처음으로 사실을 인정함", "change_type": "인정", "article_ids": [11, 11, 999]},
    ]}
    res = fx.validate(ev, raw)
    assert [f["fact"][:5] for f in res["facts"]] == ["OO 보도", "대표 측이"]
    assert res["facts"][1]["article_ids"] == [11] and res["facts"][1]["needs_review"] is True
    assert res["dropped"] == 4 and res["title"] == "OO기업 대표 의혹" and res["verification"] == "보도된 의혹"


def test_validate_ignores_title_for_existing_event_and_bad_verification():
    ev = fx.EventInput("E1", 7, "기존 사건", [], [art(1)])
    res = fx.validate(ev, {"title": "새 이름", "verification": "확실함", "new_facts": []})
    assert res["title"] is None and res["verification"] is None


def test_press_channels_filtered():
    from morning_brief.daily import is_press
    assert is_press("연합뉴스TV") and is_press("MBN News") and is_press("채널A 김진의 돌직구쇼") and is_press("서울신문")
    assert not is_press("장르만 여의도") and not is_press("이돈호 변호사") and not is_press("슈카월드")


def test_update_notice_lists_fresh_cards_only():
    from datetime import date
    from morning_brief import update
    msg = update.notice("16시", date(2026, 11, 18), [{"title": "새 사건", "why_now": "오후 발표"}])
    assert msg.startswith("🔄 16시 업데이트 — 11월 18일")
    assert "• 새 사건" in msg and "오후 발표" in msg


def test_rank_mixes_morning_and_update_cards():
    from morning_brief import daily
    def card(eid, base, imp=0.5):
        return {"event_id": eid, "score": {"base": base, "importance": imp}}
    top, ext = daily.rank([card(i, float(i)) for i in range(1, 9)], {})
    assert [b["event_id"] for b in top] == [8, 7, 6, 5, 4]
    assert {b["event_id"] for b in ext} == {1, 2, 3}


def test_embed_cache_reuses_vectors(tmp_path, monkeypatch):
    from morning_brief import daily, llm
    monkeypatch.setattr(daily, "EMBED_CACHE", str(tmp_path / "e.npz"))
    calls = []
    def fake(texts, force_model=None):
        calls.append(len(texts))
        return np.stack([unit(1, len(t), 0) for t in texts]), "bge-m3"
    monkeypatch.setattr(llm, "embed", fake)
    v1, m = daily.embed_articles([art(1, title="aa"), art(2, title="bbb")])
    v2, _ = daily.embed_articles([art(2, title="bbb"), art(3, title="c")])
    assert calls == [2, 1] and m == "bge-m3"
    assert np.allclose(v1[1], v2[0])
