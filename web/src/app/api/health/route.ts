import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { hasDb, sql } from "@/lib/db";

// 로그인한 사람만 볼 수 있는 점검 화면: DB 연결과 테이블 상태 (비밀번호 등은 출력하지 않음)
export async function GET() {
  await requireUser();
  const out: Record<string, unknown> = { db_url_set: hasDb() };
  if (hasDb()) {
    const url = new URL(process.env.DATABASE_URL!);
    out.db_host = `${url.hostname}:${url.port}`;
    out.db_user = url.username;
    try {
      const [r] = await sql()<{ cards: number; schedules: number; last: string | null }[]>`
        select (select count(*)::int from card) as cards, (select count(*)::int from schedule) as schedules,
               (select max(base_date)::text from card) as last`;
      out.ok = true;
      Object.assign(out, r);
    } catch (e) {
      out.ok = false;
      out.error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
      const code = (e as { code?: string }).code;
      if (code) out.code = code;
    }
  }
  return NextResponse.json(out);
}
