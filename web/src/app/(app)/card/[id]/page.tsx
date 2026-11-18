import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CardDetail } from "@/components/CardDetail";
import { PrintButton } from "@/components/PrintButton";
import { cardById } from "@/lib/data";

async function load(id: string) {
  const n = Number(id);
  return Number.isInteger(n) && n > 0 ? cardById(n) : null;
}

export async function generateMetadata({ params }: PageProps<"/card/[id]">): Promise<Metadata> {
  const card = await load((await params).id);
  return { title: card?.body.title ?? "카드" };
}

export default async function CardPage({ params }: PageProps<"/card/[id]">) {
  const card = await load((await params).id);
  if (!card) notFound();
  return (
    <main className="page">
      <div className="head no-print">
        <Link href={`/?d=${card.base_date}`}>← {card.base_date} 카드 목록</Link>
        <div className="tools"><PrintButton label="이 카드 인쇄 / PDF" /></div>
      </div>
      <CardDetail card={card} />
    </main>
  );
}
