import type { Metadata } from "next";
import Link from "next/link";
import { VerifBadge } from "@/components/Badges";
import { CardDetail } from "@/components/CardDetail";
import { PrintButton } from "@/components/PrintButton";
import { cardDates, cardsFor } from "@/lib/data";
import { dateKo, isYmd } from "@/lib/format";

export const metadata: Metadata = { title: "브리핑 묶음 인쇄" };

/** 오늘의 브리핑 묶음: 표지 1장 + 카드 1장씩 */
export default async function PrintBundle({ searchParams }: PageProps<"/print">) {
  const { d } = await searchParams;
  const date = isYmd(typeof d === "string" ? d : null) ? (d as string) : (await cardDates(1))[0];
  const cards = date ? await cardsFor(date) : [];
  const top = cards.filter((c) => c.kind === "top");
  const ext = cards.filter((c) => c.kind === "extension");

  return (
    <main className="page">
      <div className="head no-print">
        <div>
          <Link href={date ? `/?d=${date}` : "/"}>← 카드 목록</Link>
          <p className="print-note">표지 1장 + 카드 {cards.length}장. 인쇄 창에서 &lsquo;PDF로 저장&rsquo;을 고르면 파일로 받을 수 있어요.</p>
        </div>
        <div className="tools"><PrintButton /></div>
      </div>

      <section className="cover sheet">
        <p className="eyebrow">아침 브리핑</p>
        <h1>{date ? dateKo(date) : "카드 없음"}</h1>
        <div className="part">
          <h2>오늘 꼭 알아야 할 뉴스</h2>
          <ol>
            {top.map((c) => (
              <li key={c.id}>
                <b>{c.body.title}</b> <VerifBadge v={c.body.verification} />
                {c.body.why_now && <p>{c.body.why_now}</p>}
              </li>
            ))}
          </ol>
        </div>
        {ext.length > 0 && (
          <div className="part">
            <h2>더 볼 만한 소재</h2>
            <ul>{ext.map((c) => <li key={c.id}>{c.body.title}</li>)}</ul>
          </div>
        )}
      </section>

      {cards.map((c) => (
        <div className="sheet" key={c.id}><CardDetail card={c} /></div>
      ))}
    </main>
  );
}
