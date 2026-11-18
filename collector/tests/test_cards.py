from datetime import date

from morning_brief.deliver import briefing
from morning_brief.pipeline.cards import validate


def test_validate_card_keeps_only_allowed_values():
    raw = {
        "why_now": "공정위가 현장조사에 착수했다.", "importance": 1.7,
        "new_fact_ids": [5, 999],
        "perspectives": [{"group": "통신사", "emphasis": "조사 착수 사실 위주"},
                         {"group": "진보언론", "emphasis": "성향 라벨"}],
        "core_conflict": ["공정 경쟁 vs 가족 경영", "x", "y"],
        "questions": {"opening": "왜 지금?", "followups": ["1", "2", "3", "4"]},
        "prepare": {"expert_fields": ["공정거래"]},
    }
    v = validate(raw, [5, 6], {"통신사", "경제지"})
    assert v["importance"] == 1.0 and v["new_fact_ids"] == [5]
    assert [p["group"] for p in v["perspectives"]] == ["통신사"]
    assert len(v["core_conflict"]) == 2 and len(v["questions"]["followups"]) == 3
    assert v["prepare"]["expert_fields"] == ["공정거래"]


def test_validate_falls_back_to_today_facts():
    v = validate({}, [7, 8, 9, 10], set())
    assert v["new_fact_ids"] == [7, 8, 9]


def test_briefing_text_marks_allegations():
    card = {"title": "OO 의혹", "verification": "보도된 의혹", "why_now": "새 보도"}
    msg = briefing.text(date(2026, 11, 16), [card], [dict(card, title="확장")])
    assert "11월 16일 (월)" in msg and "1. OO 의혹 [보도된 의혹]" in msg and "• 확장" in msg


def test_people_must_appear_in_cited_article():
    from morning_brief.pipeline.cards import _ai, _people
    arts = [{"id": 1, "title": "최민희 최고위원 발언 논란", "summary": "정청래 대표가 유감을 표했다"},
            {"id": 2, "title": "세무사 시험 A씨 자백", "summary": None}]
    raw = [{"name": "최민희", "role": "최고위원", "why": "당사자", "article_ids": [1]},
           {"name": "정청래", "role": "대표", "article_ids": [1, 2]},      # 2번 기사엔 없음 → 1만 남음
           {"name": "홍길동", "role": "의원", "article_ids": [1]},          # 기사에 없는 이름 → 제외
           {"name": "A씨", "role": "수험생", "article_ids": [2]},           # 일반인 → 제외
           {"name": "최민희", "article_ids": [1]}]                          # 중복 → 제외
    got = _people(raw, arts)
    assert [p["name"] for p in got] == ["최민희", "정청래"]
    assert got[1]["article_ids"] == [1]
    ai = _ai([{"name": "최민희"}, {"name": "김교수", "role": "정치학"}, {"name": "B씨"}], {"최민희"})
    assert [p["name"] for p in ai] == ["김교수"]
