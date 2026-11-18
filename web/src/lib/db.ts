import postgres from "postgres";

// 서버에서만 쓴다. DATABASE_URL은 Vercel 환경변수에만 둔다 (브라우저로 나가지 않음).
const g = globalThis as unknown as { _sql?: postgres.Sql };

export function hasDb(): boolean {
  return !!process.env.DATABASE_URL;
}

export function sql(): postgres.Sql {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL이 설정되지 않았습니다.");
  g._sql ??= postgres(url, { max: 3, prepare: false, idle_timeout: 20, connect_timeout: 15, ssl: "require" });
  return g._sql;
}
