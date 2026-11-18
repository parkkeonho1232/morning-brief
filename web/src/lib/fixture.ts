// 로컬 화면 확인용 예시 데이터 (DATABASE_URL이 없을 때만 쓰임). 실제 기사·사실이 아니다.
import type { Card, CardBody, Schedule } from "./types";

const src = (source: string, path: string) => ({
  source, url: `https://example.com/${path}`, title: `${source} 예시 기사`, paywall: false, via: null,
});

function body(p: Partial<CardBody> & Pick<CardBody, "title" | "verification">): CardBody {
  return {
    event_id: 1, why_now: null, new_facts: [], signals: { sources: 4, sources_growth: 2, change_strength: 2.5 },
    perspectives: [], core_conflict: [], questions: { opening: null, followups: [] },
    prepare: { expert_fields: [], visuals: [], checks: [] }, schedules: [], timeline: [],
    score: { base: 5, importance: 0.6 }, ...p,
  };
}

const D = "2026-11-16";

export const FIXTURE_CARDS: Card[] = [
  {
    id: 1, base_date: D, kind: "top", rank: 1,
    body: body({
      title: "[예시] 자격시험 AI 부정행위 자백", verification: "공식 확인",
      why_now: "[예시] 수석 합격자 A씨가 초소형 카메라와 AI를 썼다고 자백하면서 시험 관리 문제가 커졌다.",
      new_facts: [
        { id: 11, fact: "[예시] 시험 주관 기관이 합격 취소 절차에 들어갔다.", change_type: "공식 조치", needs_review: false,
          sources: [src("연합뉴스", "a1"), src("KBS", "a2")] },
        { id: 12, fact: "[예시] A씨는 조사에서 부정행위를 인정했다.", change_type: "인정", needs_review: true,
          sources: [src("SBS", "a3")] },
      ],
      perspectives: [{ group: "방송", emphasis: "[예시] 시험 관리 허점" }, { group: "통신", emphasis: "[예시] 수사 진행 상황" }],
      core_conflict: ["시험의 공정성", "기술 발전 속도"],
      questions: { opening: "[예시] AI 시대에 시험은 무엇을 재야 할까?", followups: ["[예시] 감독 방식은?", "[예시] 다른 시험은 안전한가?", "[예시] 처벌 수위는?"] },
      prepare: { expert_fields: ["교육평가"], visuals: ["시험장 자료화면"], checks: ["기관 공식 발표문"] },
      people: [{ name: "[예시] 홍길동", role: "시험 주관 기관장", why: "공식 입장 발표", article_ids: [1], sources: [{ source: "연합뉴스", url: "https://example.com/a1" }] }],
      videos: [{ channel: "[예시] 시사 채널", title: "[예시] AI 부정행위, 어디까지 막을 수 있나", url: "https://example.com/v1", views: 182000 }],
      ai_suggestions: [{ name: "[예시] 김교수", role: "교육평가 전공", why: "시험 제도 설명" }],
      schedules: [{ org: "국회", title: "[예시] 교육위원회 전체회의", kind: "위원회", starts_at: "11-18 10:00", all_day: false, sim: 0.61 }],
      timeline: [{ date: "2026-11-15", change_type: "최초 보도", fact: "[예시] 부정행위 의혹이 처음 보도됐다." },
                 { date: D, change_type: "인정", fact: "[예시] A씨는 조사에서 부정행위를 인정했다." }],
    }),
  },
  {
    id: 2, base_date: D, kind: "top", rank: 2,
    body: body({
      title: "[예시] 의원 발언 논란과 당내 대응", verification: "당사자 반박", edition: "16시",
      why_now: "[예시] 발언 영상이 퍼지면서 당 지도부가 입장을 냈다.",
      new_facts: [{ id: 21, fact: "[예시] OO 보도에 따르면 당내 징계 요구가 제기됐다.", change_type: "확장", needs_review: false,
                    sources: [src("한겨레", "b1")] }],
    }),
  },
  {
    id: 3, base_date: D, kind: "extension", rank: 1,
    body: body({
      title: "[예시] 해외 부동산 개발사 대규모 유상증자", verification: "공식 확인",
      why_now: "[예시] 32억 달러 규모 증자 제안이 공시됐다.",
      new_facts: [{ id: 31, fact: "[예시] 회사가 유상증자 계획을 공시했다.", change_type: "공식 조치", needs_review: false,
                    sources: [src("Reuters", "c1")] }],
    }),
  },
];

export const FIXTURE_SCHEDULES: Schedule[] = [
  { org: "국회", title: "[예시] 본회의", starts_at: new Date(`${D}T14:00:00+09:00`), all_day: false, kind: "본회의", place: "본회의장" },
  { org: "국회", title: "[예시] 교육위원회 전체회의", starts_at: new Date("2026-11-18T10:00:00+09:00"), all_day: false, kind: "위원회", place: null },
  { org: "한국은행", title: "금융통화위원회 통화정책방향 결정", starts_at: new Date("2026-11-26T00:00:00+09:00"), all_day: true, kind: "금통위", place: null },
];
