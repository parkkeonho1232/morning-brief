import os

import httpx


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"


def _check(r: httpx.Response):
    """오류 메시지에 봇 토큰이 들어간 URL이 찍히지 않게 상태 코드만 남긴다."""
    if not r.is_success:
        raise RuntimeError(f"Telegram HTTP {r.status_code}")


def send(text: str, alert: bool = False) -> bool:
    """텔레그램 메시지 발송. 받는 사람은 TELEGRAM_CHAT_ID (쉼표로 여러 명).

    alert=True(운영 경고)는 TELEGRAM_ADMIN_CHAT_ID가 있으면 그 사람에게만 간다.
    토큰이 없으면 조용히 건너뛴다 (로컬 실행용). 한 명이라도 성공하면 True.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    raw = (alert and os.environ.get("TELEGRAM_ADMIN_CHAT_ID")) or os.environ.get("TELEGRAM_CHAT_ID") or ""
    chats = [c.strip() for c in raw.split(",") if c.strip()]
    if not token or not chats:
        return False
    ok = False
    for chat in chats:
        try:
            r = httpx.post(_api("sendMessage"),
                           json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=15)
            ok = r.is_success or ok
        except httpx.HTTPError:
            pass
    return ok


def recent_chats() -> list[dict]:
    """봇에게 최근 말을 건 사람들의 chat id (새 수신자 등록용). 메시지 내용은 읽지 않는다."""
    r = httpx.get(_api("getUpdates"), timeout=15)
    _check(r)
    seen: dict[int, dict] = {}
    for u in r.json().get("result", []):
        chat = (u.get("message") or u.get("my_chat_member") or {}).get("chat")
        if chat and chat.get("type") == "private":
            seen[chat["id"]] = {"chat_id": chat["id"],
                                "name": " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])),
                                "username": chat.get("username")}
    return list(seen.values())


def bot_info() -> dict:
    r = httpx.get(_api("getMe"), timeout=15)
    _check(r)
    return r.json().get("result", {})
