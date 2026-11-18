import Link from "next/link";
import { requireUser } from "@/lib/auth";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  await requireUser();
  return (
    <>
      <header className="top">
        <div className="top-in">
          <Link href="/" className="brand">아침<span>브리핑</span></Link>
          <nav className="nav" aria-label="메뉴">
            <Link href="/">오늘</Link>
            <Link href="/week">이번 주 일정</Link>
          </nav>
          <div className="who">
            <form action="/auth/signout" method="post"><button>로그아웃</button></form>
          </div>
        </div>
      </header>
      {children}
    </>
  );
}
