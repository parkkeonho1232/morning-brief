"""오후 업데이트 (16:00·20:00 KST): 아침 배치 뒤에 나온 기사로 오늘 카드를 새로 고친다.

- 오늘 05:30 ~ 지금 기사를 묶고 진행 중인 사건에 이어 붙여, 아침 이후 새 사실을 찾는다.
- 이 중간 결과(묶음·새 사실·새 사건)는 '내일 기준일'(D+1)로 저장한다. 내일 아침 배치가 reset_day(D+1)로
  지우고 전날 05:30~당일 05:30 전체로 다시 계산하므로, 아침 브리핑의 '어제 대비 변화'는 그대로다.
  같은 이유로 20시 업데이트는 16시 결과를 지우고 05:30~20:00으로 다시 계산한다.
- 카드: 직전 회차 카드 + 새로 바뀐 사건 카드를 합쳐 순위를 다시 매겨 오늘(D)의 이번 회차(card.edition)로 저장한다.
  아침·16시·20시 카드는 회차별로 따로 남아 대시보드에서 골라 볼 수 있다.
  새로 만든 카드에는 body.edition("16시")을 붙여 '새 소식'으로 표시한다.
- 텔레그램: 새 카드가 Top·확장에 들어갔을 때만 짧게 알린다. 메일은 보내지 않는다.
"""
import json
import os
import time as _time
from datetime import date, datetime, timedelta, timezone

from . import config, db, llm
from .daily import build_cards, process, rank, save_cards, window, youtube_search
from .deliver import telegram
from .pipeline.normalize import KST


def notice(label: str, d, fresh: list[dict]) -> str:
    lines = [f"🔄 {label} 업데이트 — {d.month}월 {d.day}일", "아침 이후 새로 바뀐 아이템", ""]
    for b in fresh:
        lines.append(f"• {b['title']}")
        if b.get("why_now"):
            lines.append(f"   └ {b['why_now']}")
    url = os.environ.get("DASHBOARD_URL")
    if url:
        lines += ["", f"대시보드: {url}"]
    return "\n".join(lines)[:4000]


def slot_label(hour: int) -> str:
    """실제 시작 시각이 늦어져도(예: 16:20) 예정된 회차 이름(16시)으로 저장한다."""
    slots = sorted(int(s.split(":")[0]) for s in config.ops()["daily"]["updates"])
    return f"{max((h for h in slots if h <= hour), default=slots[0])}시"


def edition_order(e: str) -> int:
    return 0 if e == "아침" else int(e.rstrip("시"))


def run(d: date | None = None, send: bool = True) -> int:
    """d를 주면 그날 카드를 갱신한다 (시험·재실행용, 창은 그날 05:30 ~ 다음 날 05:30 안에서 지금까지)."""
    real_now = datetime.now(timezone.utc)
    d = d or real_now.astimezone(KST).date()
    start = window(d)[1]                       # 그날 05:30
    now = min(real_now, start + timedelta(days=1))
    if now <= start:
        print(f"update: {d} 아침 배치 전이라 건너뜀")
        return 0
    label = slot_label(real_now.astimezone(KST).hour)
    p = d + timedelta(days=1)                  # 임시 기준일 (다음 날 아침 배치가 지우고 다시 계산)
    cfg = config.ops()["pipeline"]
    detail: dict = {"base_date": d.isoformat(), "label": label, "steps": {}}
    t0 = _time.monotonic()

    def step(name, **info):
        detail["steps"][name] = {**info, "t": round(_time.monotonic() - t0, 1)}
        print(f"update {name}: {json.dumps(info, ensure_ascii=False)}")

    with db.connect() as conn:
        log_id = conn.execute("insert into run_log (job, step) values ('update', 'start') returning id").fetchone()["id"]
        conn.commit()
        try:
            model = process(conn, p, start, now, now, cfg, step)

            built, n_cands, failed = build_cards(conn, p, model, cfg, start, now, cfg.get("update_card_candidates", 8))
            for b in built:
                b["edition"] = label
            rows = conn.execute(
                """select c.edition, c.body from card c where c.base_date = %s and c.edition <> %s
                     and exists (select 1 from event e where e.id = c.event_id)""", (d, label)).fetchall()
            prev = max({r["edition"] for r in rows}, key=edition_order, default=None)   # 직전 회차
            old = [r["body"] for r in rows if r["edition"] == prev]
            old_base = {b["event_id"]: b["score"]["base"] for b in old}
            for b in built:                    # 아침 카드가 있던 사건은 둘 중 높은 점수로 순위를 매긴다
                b["score"]["base"] = max(b["score"]["base"], old_base.get(b["event_id"], 0))
            rebuilt = {b["event_id"] for b in built}
            top, ext = rank([b for b in old if b["event_id"] not in rebuilt] + built, cfg)
            fresh = [b for b in top + ext if b in built]
            yt = youtube_search(fresh, d)
            save_cards(conn, d, top, ext, label)
            conn.commit()
            step("cards", candidates=n_cands, built=len(built), failed=failed, kept=len(top) + len(ext) - len(fresh),
                 fresh=len(fresh), **yt)

            sent = bool(fresh) and send and telegram.send(notice(label, d, fresh))
            step("notice", telegram=sent)
            detail["llm"] = {"calls": llm.usage.calls, "fallbacks": llm.usage.fallbacks}
            conn.execute("update run_log set finished_at = now(), ok = true, step = 'notice', detail = %s where id = %s",
                         (json.dumps(detail, ensure_ascii=False), log_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            detail["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            conn.execute("update run_log set finished_at = now(), ok = false, detail = %s where id = %s",
                         (json.dumps(detail, ensure_ascii=False), log_id))
            conn.commit()
            if send:
                telegram.send(f"⚠️ {label} 업데이트 실패 ({d}) — 아침 카드는 그대로예요\n{detail['error']}", alert=True)
            raise
    print(f"update done in {_time.monotonic() - t0:.0f}s llm={llm.usage.calls}")
    return 0
