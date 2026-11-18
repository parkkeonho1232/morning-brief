const V: Record<string, string> = { "공식 확인": "v-ok", "보도된 의혹": "v-warn", "당사자 반박": "v-rebut", "확인 대기": "v-wait" };

export function VerifBadge({ v }: { v: string }) {
  return <span className={`badge ${V[v] ?? "v-wait"}`}>{v}</span>;
}
