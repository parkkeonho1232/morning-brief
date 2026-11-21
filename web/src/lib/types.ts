// collector/morning-brief/pipeline/cards.py build()가 만드는 card.body 구조

export type Verification = "공식 확인" | "보도된 의혹" | "당사자 반박" | "확인 대기";

export type Source = { source: string; url: string; title: string; paywall: boolean; via: string | null };

export type Fact = {
  id: number;
  fact: string;
  change_type: string;
  needs_review: boolean;
  sources: Source[];
};

export type CardSchedule = {
  org: string;
  title: string;
  kind: string | null;
  starts_at: string; // "MM-DD HH:MM" (KST)
  all_day: boolean;
  sim: number;
};

export type Person = { name: string; role: string | null; why: string | null };

export type CardBody = {
  event_id: number;
  title: string;
  verification: Verification | string;
  why_now: string | null;
  new_facts: Fact[];
  signals: {
    sources?: number;
    sources_growth?: number;
    change_strength?: number;
    intl_and_domestic?: boolean;
    schedules_7d?: number;
    new_event?: boolean;
  };
  perspectives: { group: string; emphasis: string }[];
  core_conflict: string[];
  questions: { opening: string | null; followups: string[] };
  prepare: { expert_fields: string[]; visuals: string[]; checks: string[] };
  schedules: CardSchedule[];
  /** 기사 제목·요약에 이름이 실제로 나온 인물 (코드 검증) */
  people?: (Person & { article_ids: number[]; sources: { source: string; url: string }[] })[];
  /** AI가 떠올린 관련 인물 — 기사 근거 없음, 확인 필요 */
  ai_suggestions?: Person[];
  /** 이 사건을 다룬 시사 유튜브 영상 */
  videos?: { channel: string; title: string | null; url: string; views: number | null }[];
  /** 오후 업데이트에서 새로 만든 카드면 "16시"·"20시" */
  edition?: string;
  timeline: { date: string; change_type: string; fact: string }[];
  score: { base: number; importance: number; top?: number };
};

export type Card = {
  id: number;
  base_date: string; // YYYY-MM-DD
  edition: string; // 아침 | 16시 | 20시
  kind: "top" | "extension";
  rank: number;
  body: CardBody;
};

export type Schedule = {
  org: string;
  title: string;
  starts_at: Date;
  all_day: boolean;
  kind: string | null;
  place: string | null;
};

export type RunInfo = { job: string; finished_at: Date | null; ok: boolean | null } | null;
