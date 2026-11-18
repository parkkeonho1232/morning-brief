"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { COOKIE, MAX_AGE_S, checkLogin, makeToken } from "@/lib/session";

export async function login(_prev: string | null, form: FormData): Promise<string | null> {
  const user = String(form.get("user") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!(await checkLogin(user, password))) {
    await new Promise((r) => setTimeout(r, 1200)); // 마구 대입하는 시도를 늦춘다
    return "아이디나 비밀번호가 맞지 않아요.";
  }
  (await cookies()).set(COOKIE, await makeToken(), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: MAX_AGE_S,
  });
  redirect("/");
}
