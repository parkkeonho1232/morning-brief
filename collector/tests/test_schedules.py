from datetime import datetime

from morning_brief.pipeline.normalize import KST
from morning_brief.sources.schedules import bok_mpc, parse_assembly


def test_parse_assembly_event_with_time_range():
    s = parse_assembly({"SCH_KIND": "국회행사", "SCH_CN": "기업의 물리적 기후위험 관리", "SCH_DT": "2026-11-19",
                        "SCH_TM": "14:30~16:20", "CONF_DIV": None, "CMIT_NM": None,
                        "EV_INST_NM": "김소희·박정현 의원실", "EV_PLC": "의원회관 신관 제3세미나실"})
    assert s.title == "기업의 물리적 기후위험 관리"
    assert s.starts_at == datetime(2026, 11, 19, 14, 30, tzinfo=KST)
    assert not s.all_day and s.kind == "국회행사" and s.host == "김소희·박정현 의원실"


def test_parse_assembly_committee_without_time():
    s = parse_assembly({"SCH_KIND": "위원회", "SCH_CN": "전체회의", "SCH_DT": "2026-11-20", "SCH_TM": "",
                        "CMIT_NM": "법제사법위원회", "CONF_DIV": None})
    assert s.title == "법제사법위원회 전체회의"
    assert s.all_day and s.starts_at == datetime(2026, 11, 20, tzinfo=KST)


def test_parse_assembly_rejects_empty():
    assert parse_assembly({"SCH_DT": "2026-11-20"}) is None
    assert parse_assembly({"SCH_CN": "x"}) is None


def test_bok_mpc_from_ops():
    items = bok_mpc()
    assert items[0].starts_at == datetime(2026, 11, 26, 9, 0, tzinfo=KST)
    assert all(i.org == "한국은행" for i in items)
