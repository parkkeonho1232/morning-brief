"""① 정규화: URL·제목·요약·발행시각. 본문 저장을 막기 위해 요약은 SUMMARY_MAX자로 자른다."""
import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KST = timezone(timedelta(hours=9))
SUMMARY_MAX = 300

_TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|ref$|from$|plink$|cmpid$|ocid$)", re.I)
_TAG = re.compile(r"</?[A-Za-z][^>]*>")   # 진짜 HTML 태그만. <인간 없는 전쟁> 같은 작품명 꺾쇠는 보존
_WS = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(query), ""))


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(_TAG.sub(" ", html.unescape(s)))
    return _WS.sub(" ", s).strip()


def clean_summary(s: str | None) -> str | None:
    s = clean_text(s)
    if len(s) < 20:
        return None
    return s if len(s) <= SUMMARY_MAX else s[: SUMMARY_MAX - 1].rstrip() + "…"


# 기사가 아닌 방송 프로그램·섹션 페이지 제목 (MBC·KBS 쪽에서 섞여 들어옴)
_JUNK_TITLE = re.compile(
    r"\[?[^\]]{0,20}클로징\]?|\[?(뉴스데스크|뉴스투데이|뉴스\s?9|최신\s?뉴스|주요\s?뉴스|많이 본 뉴스)\]?"
    r"|정치|경제|사회|국제|세계|문화|연예|스포츠|날씨|오피니언|IT|과학")


def is_junk_title(title: str) -> bool:
    t = title.strip()
    return len(t) < 8 or bool(_JUNK_TITLE.fullmatch(t))


def title_hash(title: str) -> str:
    key = re.sub(r"[\W_]+", "", title.lower())
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def parse_dt(s: str | None, naive_tz=KST) -> datetime | None:
    """RFC 822, ISO 8601, 'YYYY-MM-DD HH:MM:SS'를 UTC로. 시간대가 없으면 naive_tz로 간주."""
    if not s or not s.strip():
        return None
    s = s.strip()
    d = None
    try:
        # 'Sun, 15 Nov 2026 20:59:19 +09:00' 같은 비표준 오프셋 보정
        d = parsedate_to_datetime(re.sub(r"([+-]\d\d):(\d\d)$", r"\1\2", s))
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=naive_tz)
    return d.astimezone(timezone.utc)
