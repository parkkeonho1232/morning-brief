"""아침 브리핑 텔레그램 메시지: Top 5 제목 + 한 줄 '왜 지금' + 확장 소재 + 대시보드 링크."""
import os
from datetime import date


WEEKDAY = "월화수목금토일"
LIMIT = 4000          # 텔레그램 메시지 4096자 제한


def text(d: date, top: list[dict], ext: list[dict]) -> str:
    lines = [f"📰 오늘의 아이템 — {d.month}월 {d.day}일 ({WEEKDAY[d.weekday()]})", ""]
    if not top:
        lines.append("오늘은 카드로 만들 만한 변화가 없었어요.")
    else:
        lines.append("■ 오늘 꼭 알아야 할 뉴스")
        for i, c in enumerate(top, 1):
            tag = f" [{c['verification']}]" if c["verification"] in ("보도된 의혹", "당사자 반박") else ""
            lines.append(f"{i}. {c['title']}{tag}")
            if c.get("why_now"):
                lines.append(f"   └ {c['why_now']}")
    if ext:
        lines += ["", "■ 더 볼 만한 소재"]
        for c in ext:
            lines.append(f"• {c['title']}")
    url = os.environ.get("DASHBOARD_URL")
    if url:
        lines += ["", f"대시보드: {url}"]
    msg = "\n".join(lines)
    return msg if len(msg) <= LIMIT else msg[: LIMIT - 1] + "…"
