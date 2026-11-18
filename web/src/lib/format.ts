// 화면 기준은 KST (CLAUDE.md: DB는 UTC 저장, 화면·배치는 KST)

const WEEKDAY = "일월화수목금토";
const KST = "Asia/Seoul";

export function todayKST(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: KST }).format(new Date());
}

export function addDays(ymd: string, n: number): string {
  const d = new Date(`${ymd}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** "2026-11-16" → "11월 16일 (월)" */
export function dateKo(ymd: string): string {
  const d = new Date(`${ymd}T00:00:00Z`);
  return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 (${WEEKDAY[d.getUTCDay()]})`;
}

export function ymdKST(t: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: KST }).format(t);
}

export function timeKST(t: Date): string {
  return new Intl.DateTimeFormat("ko-KR", { timeZone: KST, hour: "2-digit", minute: "2-digit", hour12: false }).format(t);
}

export function isYmd(s: string | undefined | null): s is string {
  return !!s && /^\d{4}-\d{2}-\d{2}$/.test(s);
}

/** 인쇄용 짧은 주소: "https://www.kbs.co.kr/news/view.do?ncd=123" → "kbs.co.kr/news/view.do…" */
export function shortUrl(url: string, max = 38): string {
  try {
    const u = new URL(url);
    const s = u.hostname.replace(/^www\./, "") + u.pathname + (u.search ? "?" : "");
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  } catch {
    return url.slice(0, max);
  }
}
