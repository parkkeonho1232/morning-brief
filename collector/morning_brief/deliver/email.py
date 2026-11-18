"""아침 브리핑 메일: 텔레그램보다 자세한 카드 전체를 HTML로. Gmail SMTP + 앱 비밀번호.

env: GMAIL_USER, GMAIL_APP_PASSWORD, BRIEFING_EMAIL_TO (쉼표로 여러 명). 없으면 조용히 건너뛴다.
"""
import os
import smtplib
from datetime import date
from email.message import EmailMessage
from html import escape

from . import briefing

WARN = ("보도된 의혹", "당사자 반박")


def _e(x) -> str:
    return escape(str(x)) if x is not None else ""


def _list(items, label: str) -> str:
    items = [i for i in items or [] if i]
    if not items:
        return ""
    return f"<p style='margin:6px 0 2px;color:#555;font-size:13px'><b>{label}</b></p><ul style='margin:0 0 4px 18px;padding:0'>" \
           + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>"


def _person(p: dict) -> str:
    s = p["name"] + (f" ({p['role']})" if p.get("role") else "")
    return s + (f" — {p['why']}" if p.get("why") else "")


def _views(n) -> str:
    return f" (조회 {n:,})" if n else ""


def _videos(videos) -> str:
    if not videos:
        return ""
    items = "".join(
        f"<li><a href='{_e(v['url'])}' style='color:#1a5fb4'>{_e(v['channel'])}</a>{' · ' + _e(v['title']) if v.get('title') else ''}"
        f"{_views(v.get('views'))}</li>" for v in videos)
    return ("<p style='margin:6px 0 2px;color:#555;font-size:13px'><b>이 사건을 다룬 유튜버·채널</b></p>"
            f"<ul style='margin:0 0 4px 18px;padding:0'>{items}</ul>")


def _card(i: int, c: dict) -> str:
    verif = c.get("verification") or ""
    badge_bg = "#fdecea" if verif in WARN else "#eef3f8"
    facts = ""
    for f in c.get("new_facts") or []:
        links = " ".join(f"<a href='{_e(s['url'])}' style='color:#1a5fb4'>{_e(s['source'])}"
                         f"{' (유료)' if s.get('paywall') else ''}</a>" for s in f.get("sources") or [])
        review = " <span style='color:#b00'>[확인 필요]</span>" if f.get("needs_review") else ""
        facts += f"<li>[{_e(f['change_type'])}] {_e(f['fact'])}{review}<br><span style='font-size:12px'>{links}</span></li>"
    persp = "".join(f"<li><b>{_e(p['group'])}</b>: {_e(p['emphasis'])}</li>" for p in c.get("perspectives") or [])
    q = c.get("questions") or {}
    prep = c.get("prepare") or {}
    sched = [f"{s['starts_at']} {s['org']} {s['title']}" for s in c.get("schedules") or []]
    html = f"""
<div style="border:1px solid #ddd;border-radius:8px;padding:14px 16px;margin:0 0 14px">
  <div style="font-size:17px;font-weight:bold">{i}. {_e(c['title'])}</div>
  <div style="margin:4px 0 8px;font-size:12px">
    <span style="background:{badge_bg};padding:2px 6px;border-radius:4px">{_e(verif)}</span>
  </div>
  {f"<p style='margin:4px 0'><b>왜 지금</b> {_e(c.get('why_now'))}</p>" if c.get("why_now") else ""}
  <p style="margin:6px 0 2px;color:#555;font-size:13px"><b>새로 확인된 사실</b></p>
  <ul style="margin:0 0 4px 18px;padding:0">{facts}</ul>
  {f"<p style='margin:6px 0 2px;color:#555;font-size:13px'><b>매체별 관점</b></p><ul style='margin:0 0 4px 18px;padding:0'>{persp}</ul>" if persp else ""}
  {f"<p style='margin:4px 0'><b>핵심 충돌</b> {' ↔ '.join(_e(x) for x in c.get('core_conflict') or [])}</p>" if c.get("core_conflict") else ""}
  {_list([q.get("opening")] + list(q.get("followups") or []), "방송 질문")}
  {_list(sched, "7일 내 일정")}
  {_list(prep.get("expert_fields"), "전문가 분야")}
  {_list([_person(p) for p in c.get("people") or []], "기사 속 인물")}
  {_videos(c.get("videos"))}
  {_list([_person(p) for p in c.get("ai_suggestions") or []], "AI 추천 인물 (기사 근거 없음 · 확인 필요)")}
  {_list(prep.get("visuals"), "자료화면")}{_list(prep.get("checks"), "추가 확인")}
</div>"""
    return html


def html(d: date, top: list[dict], ext: list[dict]) -> str:
    head = f"오늘의 아이템 — {d.month}월 {d.day}일 ({briefing.WEEKDAY[d.weekday()]})"
    body = [f"<h2 style='margin:0 0 12px'>📰 {_e(head)}</h2>"]
    if not top:
        body.append("<p>오늘은 카드로 만들 만한 변화가 없었어요.</p>")
    else:
        body.append("<h3 style='margin:8px 0'>■ 오늘 꼭 알아야 할 뉴스</h3>")
        body += [_card(i, c) for i, c in enumerate(top, 1)]
    if ext:
        body.append("<h3 style='margin:8px 0'>■ 더 볼 만한 소재</h3>")
        body += [_card(i, c) for i, c in enumerate(ext, 1)]
    url = os.environ.get("DASHBOARD_URL")
    if url:
        body.append(f"<p><a href='{_e(url)}'>대시보드 열기</a></p>")
    body.append("<p style='color:#888;font-size:12px'>기사 제목·요약 기반 자동 정리입니다. 방송 전 원문 확인이 필요해요.</p>")
    return ("<div style=\"font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
            "max-width:720px;line-height:1.5;color:#222\">" + "".join(body) + "</div>")


def send(d: date, top: list[dict], ext: list[dict]) -> bool:
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    to = [x.strip() for x in (os.environ.get("BRIEFING_EMAIL_TO") or "").split(",") if x.strip()]
    if not user or not pw or not to:
        return False
    msg = EmailMessage()
    msg["Subject"] = f"[아침 브리핑] {d.month}/{d.day} 오늘의 아이템"
    msg["From"] = f"아침 브리핑 <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(briefing.text(d, top, ext))
    msg.add_alternative(html(d, top, ext), subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw.replace(" ", ""))
        s.send_message(msg)
    return True
