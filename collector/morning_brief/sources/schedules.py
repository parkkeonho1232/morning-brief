"""공식 일정: 국회(열린국회정보 OpenAPI), 한국은행 금통위(config 수동 입력), 수동 일정(config/schedules.yaml)."""
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

from .. import config
from ..pipeline.normalize import KST, clean_text

ASSEMBLY_URL = "https://open.assembly.go.kr/portal/openapi/ALLSCHEDULE"


@dataclass
class ScheduleItem:
    org: str
    title: str
    starts_at: datetime        # KST aware
    all_day: bool = False
    url: str | None = None
    kind: str | None = None    # 국회: 본회의·위원회·국회행사 등 (SCH_KIND)
    place: str | None = None
    host: str | None = None


def fetch_assembly_raw(client: httpx.Client, day: date, size: int = 100) -> list[dict]:
    """열린국회정보 '국회일정 통합' 하루치 원본 행."""
    r = client.get(ASSEMBLY_URL, params={"KEY": os.environ["ASSEMBLY_API_KEY"], "Type": "json",
                                         "pIndex": 1, "pSize": size, "SCH_DT": day.isoformat()})
    if not r.is_success:                      # URL에 API 키가 있으므로 상태 코드만
        raise RuntimeError(f"Assembly API HTTP {r.status_code}")
    data = r.json()
    blocks = data.get("ALLSCHEDULE") or []
    for b in blocks:
        if "row" in b:
            return b["row"]
    return []


def parse_assembly(row: dict) -> ScheduleItem | None:
    day = row.get("SCH_DT")
    if not day:
        return None
    tm = (row.get("SCH_TM") or "").split("~")[0].strip()      # '14:30~16:20' → '14:30'
    try:
        starts = datetime.fromisoformat(f"{day} {tm}" if tm else day)
    except ValueError:
        starts, tm = datetime.fromisoformat(day), ""
    parts = [row.get("CMIT_NM"), row.get("CONF_DIV"), row.get("SCH_CN") or row.get("SCH_KIND")]
    title = clean_text(" ".join(p for p in parts if p))
    if not title:
        return None
    return ScheduleItem("국회", title, starts.replace(tzinfo=KST), all_day=not tm,
                        kind=row.get("SCH_KIND"), place=clean_text(row.get("EV_PLC")) or None,
                        host=clean_text(row.get("EV_INST_NM")) or None)


def assembly(client: httpx.Client, start: date, days: int) -> list[ScheduleItem]:
    out = []
    for i in range(days):
        out += [s for s in map(parse_assembly, fetch_assembly_raw(client, start + timedelta(days=i))) if s]
    return out


def bok_mpc() -> list[ScheduleItem]:
    """한은 통화정책방향 결정회의 — config/ops.yaml schedules.bok_mpc_dates (09:00 KST 회의, 10시경 발표)."""
    return [ScheduleItem("한국은행", "금융통화위원회 통화정책방향 결정회의 (기준금리 발표)",
                         datetime.fromisoformat(f"{d} 09:00").replace(tzinfo=KST))
            for d in config.ops()["schedules"].get("bok_mpc_dates") or []]


def manual() -> list[ScheduleItem]:
    """config/schedules.yaml — PD가 직접 넣는 일정(주요 통계 발표, 정부 발표 등)."""
    try:
        rows = config.load("schedules").get("items") or []
    except FileNotFoundError:
        return []
    out = []
    for r in rows:
        when = str(r["date"]) + (f" {r['time']}" if r.get("time") else "")
        out.append(ScheduleItem(r.get("org", "기타"), r["title"],
                                datetime.fromisoformat(when).replace(tzinfo=KST),
                                all_day=not r.get("time"), url=r.get("url")))
    return out
