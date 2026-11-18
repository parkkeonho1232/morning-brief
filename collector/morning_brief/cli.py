"""morning-brief collector 진입점.

  morning-brief migrate             # supabase/migrations/*.sql 중 미적용분 적용
  morning-brief sync-config         # config/*.yaml → source, yt_channel 테이블
  morning-brief collect             # 매시간: 피드 수집 → article 적재
  morning-brief collect --dry-run   # DB 없이 피드만 받아 결과 출력
  morning-brief daily               # 05:30 KST: 묶기 → 사건 연결 → 변화 감지 → 카드 → 브리핑
  morning-brief update               # 16:00·20:00 KST: 아침 이후 기사로 오늘 카드 갱신 + 새 카드 알림
  morning-brief resend --date D    # 이미 만든 카드로 텔레그램·메일만 다시 발송
  morning-brief telegram-test       # 텔레그램 연결 확인 메시지
  morning-brief check-keys          # API 키 유효성 점검 (키 값은 출력 안 함)
"""
import argparse
import os
import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="morning-brief")
    parser.add_argument("job", choices=["migrate", "sync-config", "collect", "daily", "update", "resend", "refresh-videos", "telegram-test", "telegram-chats", "check-keys", "probe-assembly", "list-models", "llm-smoke", "embed-quota", "report", "calibrate"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", help="daily 기준일 (YYYY-MM-DD, 기본: 오늘 KST)")
    parser.add_argument("--no-send", action="store_true", help="daily: 텔레그램 발송 없이 브리핑 문구만 출력")
    args = parser.parse_args()

    from . import collect, db
    if args.job == "embed-quota":
        from . import check_keys
        check_keys.embed_quota()
        sys.exit(0)
    if args.job == "llm-smoke":
        from . import check_keys
        check_keys.llm_smoke()
        sys.exit(0)
    if args.job == "list-models":
        from . import check_keys
        check_keys.list_models()
        sys.exit(0)
    if args.job == "migrate":
        from . import migrate
        sys.exit(migrate.run())
    if args.job == "probe-assembly":
        from . import check_keys
        check_keys.probe_assembly()
        sys.exit(0)
    if args.job == "check-keys":
        from . import check_keys
        sys.exit(check_keys.run())
    if args.job == "telegram-test":
        from .deliver import telegram
        ok = telegram.send("✅ 아침 브리핑 봇 연결 완료!\n매일 아침 07:30 전에 오늘의 아이템 카드를 이곳으로 보내드릴게요.")
        print("telegram: sent" if ok else "telegram: FAILED (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 확인)")
        sys.exit(0 if ok else 1)
    if args.job == "telegram-chats":
        from .deliver import telegram
        me = telegram.bot_info()
        print(f"봇 이름={me.get('first_name')}  검색어=@{me.get('username')}")
        found = telegram.recent_chats()
        public_log = os.environ.get("GITHUB_ACTIONS") == "true"   # 공개 저장소의 Actions 로그는 누구나 본다
        for c in found:
            cid, name = str(c["chat_id"]), c["name"] or "-"
            if public_log:
                cid, name = cid[:2] + "*" * (len(cid) - 4) + cid[-2:], name[:1] + "**"
            print(f"chat_id={cid}  이름={name}")
        if found and public_log:
            print("(공개 로그라 가려서 표시. 전체 chat_id는 로컬에서 `morning-brief telegram-chats`로 확인)")
        print(f"telegram-chats: {len(found)}명" if found else "telegram-chats: 없음 (봇에게 /start를 보낸 뒤 다시 실행)")
        sys.exit(0)
    if args.job == "sync-config":
        with db.connect() as conn:
            print(f"sync-config: sources={collect.sync_config(conn)}")
        sys.exit(0)
    if args.job == "collect":
        sys.exit(collect.dry_run() if args.dry_run else collect.run())
    if args.job == "calibrate":
        from datetime import date
        from . import calibrate
        sys.exit(calibrate.run(date.fromisoformat(args.date)))
    if args.job == "report":
        from datetime import date
        from . import report
        sys.exit(report.run(date.fromisoformat(args.date) if args.date else date.today()))
    if args.job == "refresh-videos":
        from datetime import date
        from . import daily
        sys.exit(daily.refresh_videos(date.fromisoformat(args.date)))
    if args.job == "update":
        from . import update
        from datetime import date
        sys.exit(update.run(date.fromisoformat(args.date) if args.date else None, send=not args.no_send))
    if args.job == "resend":
        from datetime import date
        from . import daily
        sys.exit(daily.resend(date.fromisoformat(args.date)))
    if args.job == "daily":
        from datetime import date
        from . import daily
        sys.exit(daily.run(date.fromisoformat(args.date) if args.date else None, send=not args.no_send))


if __name__ == "__main__":
    main()
