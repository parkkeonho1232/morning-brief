import type { Metadata } from "next";
import { connection } from "next/server";
import { authConfigured } from "@/lib/session";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "로그인" };

export default async function LoginPage() {
  await connection();
  return (
    <main className="login">
      <div className="login-box">
        <p className="eyebrow">아침 브리핑</p>
        <h1>편집회의 대시보드</h1>
        <p className="muted">두 분이 함께 쓰는 계정으로 로그인해 주세요. 한 번 로그인하면 30일 동안 유지돼요.</p>
        <LoginForm enabled={authConfigured()} />
      </div>
    </main>
  );
}
