import Link from "next/link";
import { CardTile } from "@/components/CardTile";
import { cardDates, cardsFor, lastDailyRun, schedules } from "@/lib/data";
import { dateKo, isYmd, timeKST, todayKST, ymdKST } from "@/lib/format";

export default async function Today({ searchParams }: PageProps<"/">) {
  const { d } = await searchParams;
  const dates = await cardDates();
  const date = isYmd(typeof d === "string" ? d : null) ? (d as string) : dates[0] ?? todayKST();
  const [cards, upcoming, run] = await Promise.all([cardsFor(date), schedules(todayKST(), 3), lastDailyRun()]);
  const top = cards.filter((c) => c.kind === "top");
  const ext = cards.filter((c) => c.kind === "extension");
  const i = dates.indexOf(date);
  const older = i >= 0 ? dates[i + 1] : dates.find((x) => x < date);
  const newer = i > 0 ? dates[i - 1] : undefined;
  const isToday = date === todayKST();

  return (
    <main className="page">
      <div className="head">
        <div>
          <p className="eyebrow">{isToday ? "오늘의 아이템" : "지난 아이템"}</p>
          <h1>{dateKo(date)}</h1>
          <p className="sub">
            {run?.finished_at
              ? `마지막 ${run.job === "update" ? "업데이트" : "아침 배치"} ${ymdKST(run.finished_at) === todayKST() ? "오늘" : ymdKST(run.finished_at)} ${timeKST(run.finished_at)}${run.ok === false ? " · 실패" : ""}`
              : "아직 실행 기록이 없어요"}
          </p>
        </div>
        <div className="tools">
          <Link className="btn" aria-disabled={!older} href={older ? `/?d=${older}` : "#"}>← 이전 날</Link>
          <Link className="btn" aria-disabled={!newer} href={newer ? `/?d=${newer}` : "#"}>다음 날 →</Link>
          {cards.length > 0 && <Link className="btn primary" href={`/print?d=${date}`}>브리핑 묶음 인쇄</Link>}
        </div>
      </div>

      <section className="block">
        <h2>오늘 꼭 알아야 할 뉴스 <small>{top.length}건</small></h2>
        {top.length ? (
          <div className="tiles">{top.map((c) => <CardTile key={c.id} card={c} />)}</div>
        ) : (
          <p className="empty">이 날은 카드로 만들 만한 변화가 없었어요.</p>
        )}
      </section>

      {ext.length > 0 && (
        <section className="block">
          <h2>더 볼 만한 소재 <small>{ext.length}건</small></h2>
          <div className="tiles">{ext.map((c) => <CardTile key={c.id} card={c} />)}</div>
        </section>
      )}

      <section className="block">
        <h2>다가오는 일정 <small>3일 · <Link href="/week">이번 주 전체</Link></small></h2>
        {upcoming.length ? (
          <ul className="agenda">
            {upcoming.slice(0, 8).map((s, k) => (
              <li key={k}>
                <span className="when">{dateKo(ymdKST(s.starts_at)).replace(/ \(.\)/, "")} {s.all_day ? "" : timeKST(s.starts_at)}</span>
                <span className="org">{s.org}</span>
                <span>{s.title}</span>
              </li>
            ))}
          </ul>
        ) : <p className="empty">3일 안에 등록된 일정이 없어요.</p>}
      </section>
    </main>
  );
}
