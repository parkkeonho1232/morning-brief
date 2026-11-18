"use client";

export function PrintButton({ label = "인쇄 / PDF 저장" }: { label?: string }) {
  return <button type="button" className="btn" onClick={() => window.print()}>{label}</button>;
}
