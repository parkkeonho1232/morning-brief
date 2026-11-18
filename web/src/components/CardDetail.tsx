import QRCode from "qrcode";
import type { Card } from "@/lib/types";
import { dateKo, shortUrl } from "@/lib/format";
import { VerifBadge } from "./Badges";

const MAX_QR = 6;

async function qrSvg(url: string): Promise<string> {
  return QRCode.toString(url, { type: "svg", margin: 0, errorCorrectionLevel: "M" });
}

function List({ items }: { items: string[] }) {
  return items.length ? <ul>{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="muted">—</p>;
}

/** 카드 전체 항목. 화면과 인쇄가 같은 컴포넌트를 쓴다. */
export async function CardDetail({ card }: { card: Card }) {
  const b = card.body;
  const sources = b.new_facts.flatMap((f) => f.sources);
  const uniq = [...new Map(sources.map((s) => [s.url, s])).values()].slice(0, MAX_QR);
  const qrs = await Promise.all(uniq.map(async (s) => ({ ...s, svg: await qrSvg(s.url) })));
  const prep = b.prepare;
  const people = b.people ?? [];
  const videos = b.videos ?? [];
  const ai = b.ai_suggestions ?? [];

  return (
    <article className="detail">
      <header>
        <p className="eyebrow">
          {dateKo(card.base_date)} · {card.kind === "top" ? `오늘 꼭 알아야 할 뉴스 ${card.rank}` : `더 볼 만한 소재 ${card.rank}`}
        </p>
        <h1>{b.title}</h1>
        <div className="row">
          <VerifBadge v={b.verification} />
          {b.edition && <span className="fresh">{b.edition} 새 소식</span>}
        </div>
        {b.why_now && <p className="why-now">{b.why_now}</p>}
        <div className="signals num">
          {b.signals.sources != null && <span>보도 매체 <b>{b.signals.sources}</b>곳</span>}
          {!!b.signals.sources_growth && <span>어제보다 <b>+{b.signals.sources_growth}</b></span>}
          {b.signals.intl_and_domestic && <span><b>국내외 동시 보도</b></span>}
          {b.signals.new_event && <span><b>오늘 처음 등장</b></span>}
        </div>
      </header>

      <section className="part">
        <h2>새로 확인된 사실</h2>
        <ul className="facts">
          {b.new_facts.map((f) => (
            <li key={f.id}>
              <div className="line">
                <span className="ctype">{f.change_type}</span>
                <span>{f.fact}</span>
                {f.needs_review && <span className="review">[확인 필요]</span>}
              </div>
              <div className="srcs">
                {f.sources.map((s, i) => (
                  <a key={i} href={s.url} target="_blank" rel="noreferrer" data-short={shortUrl(s.url)} title={s.title}>
                    {s.source}{s.paywall && <span className="paywall"> (유료)</span>}
                  </a>
                ))}
              </div>
            </li>
          ))}
        </ul>
        {qrs.length > 0 && (
          <div className="qrs" aria-hidden="true">
            {qrs.map((q, i) => (
              <div className="qr" key={i}>
                <span dangerouslySetInnerHTML={{ __html: q.svg }} />
                <span>{q.source}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {(b.perspectives.length > 0 || b.core_conflict.length > 0) && (
        <div className="two">
          {b.perspectives.length > 0 && (
            <section className="part">
              <h2>매체별 관점</h2>
              <table className="persp">
                <tbody>
                  {b.perspectives.map((p, i) => <tr key={i}><th>{p.group}</th><td>{p.emphasis}</td></tr>)}
                </tbody>
              </table>
            </section>
          )}
          {b.core_conflict.length > 0 && (
            <section className="part">
              <h2>핵심 충돌</h2>
              <p className="conflict">
                {b.core_conflict.map((c, i) => (
                  <span key={i}>{i > 0 && <span className="vs">↔ </span>}{c}</span>
                ))}
              </p>
            </section>
          )}
        </div>
      )}

      {(b.questions.opening || b.questions.followups.length > 0) && (
        <section className="part">
          <h2>방송 질문</h2>
          <div className="qs">
            {b.questions.opening && <p className="open">Q. {b.questions.opening}</p>}
            <ol>{b.questions.followups.map((q, i) => <li key={i}>{q}</li>)}</ol>
          </div>
        </section>
      )}

      <section className="part">
        <h2>인물 후보</h2>
        <div className="people">
          <div>
            <h3>기사 속 인물</h3>
            {people.length ? (
              <ul>{people.map((p, i) => (
                <li key={i}>
                  <b>{p.name}</b>{p.role && <span className="muted"> · {p.role}</span>}
                  {p.why && <span> — {p.why}</span>}
                  {p.sources.length > 0 && (
                    <span className="srcs-inline"> ({p.sources.map((s, k) => (
                      <a key={k} href={s.url} target="_blank" rel="noreferrer">{k > 0 ? ", " : ""}{s.source}</a>
                    ))})</span>
                  )}
                </li>
              ))}</ul>
            ) : <p className="muted">기사에 이름이 나온 공인이 없어요</p>}
          </div>
          <div>
            <h3>이 사건을 다룬 유튜버·채널</h3>
            {videos.length ? (
              <ul>{videos.map((v, i) => (
                <li key={i}>
                  <a href={v.url} target="_blank" rel="noreferrer">{v.channel}</a>{v.title ? ` · ${v.title}` : ""}
                  {v.views ? <span className="muted num"> · 조회 {v.views.toLocaleString("ko-KR")}</span> : null}
                </li>
              ))}</ul>
            ) : <p className="muted">관련 영상 없음</p>}
          </div>
          {ai.length > 0 && (
            <div className="ai">
              <h3>AI 추천 인물 <span className="review">기사 근거 없음 · 확인 필요</span></h3>
              <ul>{ai.map((p, i) => (
                <li key={i}><b>{p.name}</b>{p.role && <span className="muted"> · {p.role}</span>}{p.why && <span> — {p.why}</span>}</li>
              ))}</ul>
            </div>
          )}
        </div>
      </section>

      <div className="two">
        <section className="part">
          <h2>준비할 것</h2>
          <div className="qs">
            {prep.expert_fields.length > 0 && <p><b>전문가 분야</b> {prep.expert_fields.join(", ")}</p>}
            {prep.visuals.length > 0 && <p><b>자료화면</b> {prep.visuals.join(", ")}</p>}
            {prep.checks.length > 0 && <p><b>추가 확인</b> {prep.checks.join(", ")}</p>}
            {!prep.expert_fields.length && !prep.visuals.length && !prep.checks.length &&
              <p className="muted">—</p>}
          </div>
        </section>
        <section className="part">
          <h2>7일 내 관련 일정</h2>
          {b.schedules.length ? (
            <ul>{b.schedules.map((s, i) => <li key={i} className="num">{s.all_day ? s.starts_at.slice(0, 5) : s.starts_at} {s.org} · {s.title}</li>)}</ul>
          ) : <p className="muted">연결된 일정 없음</p>}
        </section>
      </div>

      {b.timeline.length > 0 && (
        <section className="part">
          <h2>사건 타임라인</h2>
          <ol className="timeline">
            {b.timeline.map((t, i) => (
              <li key={i} className={t.date === card.base_date ? "today" : ""}>
                <span className="d">{t.date.slice(5).replace("-", ".")}</span>
                <span><span className="ctype">{t.change_type}</span> {t.fact}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <p className="disclaimer">기사 제목·요약을 바탕으로 자동 정리한 내용이에요. 방송 전에 원문을 꼭 확인해 주세요. 인쇄물은 외부에 배포하지 않습니다.</p>
    </article>
  );
}
