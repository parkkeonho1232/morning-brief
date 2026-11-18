// 공용 계정 1개 로그인 세션. 쿠키 = "만료시각.서명" (HMAC-SHA256, 비밀키는 SESSION_SECRET).
// proxy(엣지)와 서버 양쪽에서 쓰므로 Web Crypto만 사용한다.

export const COOKIE = "hm_session";
export const MAX_AGE_S = 30 * 24 * 3600; // 30일 유지

export function authConfigured(): boolean {
  return !!(process.env.DASHBOARD_USER && process.env.DASHBOARD_PASSWORD && process.env.SESSION_SECRET);
}

/** 로컬 개발에서 설정이 없으면 로그인 없이 연다. 배포 환경에서는 설정이 없으면 잠근다. */
export function devBypass(): boolean {
  return !authConfigured() && process.env.NODE_ENV !== "production";
}

async function hmac(data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(process.env.SESSION_SECRET ?? ""), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  let bin = "";
  for (const b of new Uint8Array(sig)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function same(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

export async function makeToken(): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_S;
  return `${exp}.${await hmac(`${process.env.DASHBOARD_USER}|${exp}`)}`;
}

export async function validToken(token: string | undefined): Promise<boolean> {
  if (!token || !authConfigured()) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  return same(sig, await hmac(`${process.env.DASHBOARD_USER}|${exp}`));
}

/** 아이디·비밀번호 확인 (길이가 달라도 시간 차이로 드러나지 않게 해시끼리 비교) */
export async function checkLogin(user: string, password: string): Promise<boolean> {
  if (!authConfigured()) return false;
  const [a, b, c, d] = await Promise.all([
    hmac(`u:${user}`), hmac(`u:${process.env.DASHBOARD_USER}`),
    hmac(`p:${password}`), hmac(`p:${process.env.DASHBOARD_PASSWORD}`),
  ]);
  return same(a, b) && same(c, d);
}
