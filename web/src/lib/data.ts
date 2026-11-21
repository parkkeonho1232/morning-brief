import { hasDb, sql } from "./db";
import { FIXTURE_CARDS, FIXTURE_SCHEDULES } from "./fixture";
import type { Card, RunInfo, Schedule } from "./types";

// 로컬 개발에서 DATABASE_URL이 없으면 예시 데이터로 화면만 확인한다. 배포 환경에서는 반드시 DB를 쓴다.
function fixtureMode(): boolean {
  if (hasDb()) return false;
  if (process.env.NODE_ENV === "production") throw new Error("DATABASE_URL이 설정되지 않았습니다.");
  return true;
}

/** 카드가 있는 날짜 (최근 순) */
export async function cardDates(limit = 30): Promise<string[]> {
  if (fixtureMode()) return [...new Set(FIXTURE_CARDS.map((c) => c.base_date))];
  const rows = await sql()<{ d: string }[]>`
    select distinct base_date::text as d from card order by d desc limit ${limit}`;
  return rows.map((r) => r.d);
}

/** 하루 3회차. 회차마다 카드를 따로 보관한다 (collector update.py) */
export const EDITIONS = ["아침", "16시", "20시"] as const;

/** 그날 카드가 있는 회차 (아침 → 16시 → 20시 순) */
export async function editionsFor(date: string): Promise<string[]> {
  const have = fixtureMode()
    ? FIXTURE_CARDS.filter((c) => c.base_date === date).map((c) => c.edition)
    : (await sql()<{ e: string }[]>`select distinct edition as e from card where base_date = ${date}`).map((r) => r.e);
  return EDITIONS.filter((e) => have.includes(e));
}

export async function cardsFor(date: string, edition: string): Promise<Card[]> {
  if (fixtureMode()) return FIXTURE_CARDS.filter((c) => c.base_date === date && c.edition === edition);
  return sql()<Card[]>`
    select id::int, base_date::text, edition, kind, rank, body from card
    where base_date = ${date} and edition = ${edition}
    order by (kind = 'top') desc, rank`;
}

export async function cardById(id: number): Promise<Card | null> {
  if (fixtureMode()) return FIXTURE_CARDS.find((c) => c.id === id) ?? null;
  const rows = await sql()<Card[]>`
    select id::int, base_date::text, edition, kind, rank, body from card where id = ${id}`;
  return rows[0] ?? null;
}

/** [from, from+days) 기간의 공식 일정. from은 KST 날짜 */
export async function schedules(from: string, days: number): Promise<Schedule[]> {
  const start = new Date(`${from}T00:00:00+09:00`);
  const end = new Date(start.getTime() + days * 86400_000);
  if (fixtureMode()) return FIXTURE_SCHEDULES.filter((s) => s.starts_at >= start && s.starts_at < end);
  return sql()<Schedule[]>`
    select org, title, starts_at, coalesce(all_day, false) as all_day, kind, place from schedule
    where starts_at >= ${start} and starts_at < ${end}
    order by starts_at, org`;
}

export async function lastDailyRun(): Promise<RunInfo> {
  if (fixtureMode()) return { job: "daily", finished_at: new Date(), ok: true };
  const rows = await sql()<{ job: string; finished_at: Date | null; ok: boolean | null }[]>`
    select job, finished_at, ok from run_log where job in ('daily', 'update') and finished_at is not null
    order by id desc limit 1`;
  return rows[0] ?? null;
}
