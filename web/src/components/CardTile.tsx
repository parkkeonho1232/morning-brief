import Link from "next/link";
import type { Card } from "@/lib/types";
import { VerifBadge } from "./Badges";

export function CardTile({ card }: { card: Card }) {
  const b = card.body;
  const nSrc = new Set(b.new_facts.flatMap((f) => f.sources.map((s) => s.source))).size;
  const review = b.new_facts.some((f) => f.needs_review);
  return (
    <Link href={`/card/${card.id}`} className="tile">
      <div className="row">
        <span className="rank">{card.kind === "top" ? `TOP ${card.rank}` : `확장 ${card.rank}`}</span>
        <VerifBadge v={b.verification} />
        {b.edition && <span className="fresh">{b.edition} 새 소식</span>}
        {review && <span className="review">확인 필요</span>}
      </div>
      <h3>{b.title}</h3>
      {b.why_now && <p className="why">{b.why_now}</p>}
      <p className="meta num">
        새 사실 {b.new_facts.length}건 · 근거 매체 {nSrc}곳
        {b.signals.sources ? ` · 보도 ${b.signals.sources}곳` : ""}
        {b.schedules.length ? ` · 7일 내 일정 ${b.schedules.length}` : ""}
      </p>
    </Link>
  );
}
