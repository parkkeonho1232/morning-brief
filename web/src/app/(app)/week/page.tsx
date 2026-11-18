import type { Metadata } from "next";
import Link from "next/link";
import { PrintButton } from "@/components/PrintButton";
import { schedules } from "@/lib/data";
import { addDays, dateKo, isYmd, timeKST, todayKST, ymdKST } from "@/lib/format";
import type { Schedule } from "@/lib/types";

export const metadata: Metadata = { title: "이번 주 일정" };
const DAYS = 14;

export default async function Week({ searchParams }: PageProps<"/week">) {
  const { from } = await searchParams;
  const start = isYmd(typeof from === "string" ? from : null) ? (from as string) : todayKST();
  const items = await schedules(start, DAYS);
  const byDay = new Map<string, Schedule[]>();
  for (const s of items) {
    const k = ymdKST(s.starts_at);
    byDay.set(k, [...(byDay.get(k) ?? []), s]);
  }
  const days = Array.from({ length: DAYS }, (_, i) => addDays(start, i));

  return (
    <main className="page">
      <div className="head">
        <div>
          <p className="eyebrow">섭외·사전 구성용</p>
          <h1>공식 일정 {DAYS}일</h1>
          <p className="sub">{dateKo(start)} ~ {dateKo(addDays(start, DAYS - 1))} · 국회·한국은행 자동 수집, 그 밖은 config/schedules.yaml</p>
        </div>
        <div className="tools">
          <Link className="btn" href={`/week?from=${addDays(start, -7)}`}>← 7일 전</Link>
          <Link className="btn" href={`/week?from=${addDays(start, 7)}`}>7일 후 →</Link>
          <PrintButton />
        </div>
      </div>
      {days.map((d) => {
        const list = byDay.get(d) ?? [];
        return (
          <section className="block" key={d}>
            <h2>{dateKo(d)} <small>{list.length ? `${list.length}건` : "일정 없음"}</small></h2>
            {list.length > 0 && (
              <ul className="agenda">
                {list.map((s, i) => (
                  <li key={i}>
                    <span className="when">{s.all_day ? "종일" : timeKST(s.starts_at)}</span>
                    <span className="org">{s.org}</span>
                    <span>{s.title}{s.kind ? <span className="place"> · {s.kind}</span> : null}{s.place ? <span className="place"> · {s.place}</span> : null}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </main>
  );
}
