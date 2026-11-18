import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page">
      <p className="empty">찾는 화면이 없어요. <Link href="/">오늘 카드로 돌아가기</Link></p>
    </main>
  );
}
