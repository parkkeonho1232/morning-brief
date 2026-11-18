import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, authConfigured, devBypass, validToken } from "./lib/session";

// 로그인하지 않은 사람은 /login으로 보낸다.
export async function proxy(request: NextRequest) {
  if (devBypass()) return NextResponse.next();
  if (!authConfigured()) return new NextResponse("로그인 설정이 없습니다.", { status: 503 });
  const path = request.nextUrl.pathname;
  if (path === "/login") return NextResponse.next();
  if (await validToken(request.cookies.get(COOKIE)?.value)) return NextResponse.next();
  const to = request.nextUrl.clone();
  to.pathname = "/login";
  to.search = "";
  return NextResponse.redirect(to);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
