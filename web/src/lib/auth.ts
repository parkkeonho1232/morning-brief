import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { COOKIE, authConfigured, devBypass, validToken } from "./session";

/** 모든 화면에서 부른다. proxy.ts의 검사는 1차 검사이고, 이것이 실제 권한 확인이다. */
export async function requireUser(): Promise<void> {
  await connection(); // 요청마다 그린다 (빌드 때 미리 만들지 않음)
  if (devBypass()) return;
  if (!authConfigured()) throw new Error("로그인 설정(DASHBOARD_USER / DASHBOARD_PASSWORD / SESSION_SECRET)이 없습니다.");
  const store = await cookies();
  if (!(await validToken(store.get(COOKIE)?.value))) redirect("/login");
}
