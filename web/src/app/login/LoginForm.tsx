"use client";

import Link from "next/link";
import { useActionState } from "react";
import { login } from "./actions";

export function LoginForm({ enabled }: { enabled: boolean }) {
  const [error, action, pending] = useActionState(login, null);
  if (!enabled) {
    return <p className="muted">로컬 개발 모드예요. 로그인 없이 <Link href="/">대시보드</Link>로 들어갈 수 있어요.</p>;
  }
  return (
    <form action={action} className="login-form">
      <label htmlFor="user">아이디</label>
      <input id="user" name="user" autoComplete="username" autoCapitalize="none" required autoFocus />
      <label htmlFor="password">비밀번호</label>
      <input id="password" name="password" type="password" autoComplete="current-password" required />
      <button disabled={pending}>{pending ? "확인 중…" : "로그인"}</button>
      {error && <p className="err">{error}</p>}
    </form>
  );
}
