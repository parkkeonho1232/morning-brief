# morning-brief — Claude Code 작업 지침

## 프로젝트 한 줄
국내외 매체 기사를 사건 단위로 묶고, 어제 대비 변화와 방송 질문까지 정리해 매일 07:30(KST)까지 대시보드 + 아침 브리핑으로 전달하는 개인용 편집회의 툴.

기획서·작업 목록·매체 조사: `private/` (로컬 전용, .gitignore — **공개 저장소에 절대 올리지 않는다**). 항상 먼저 읽을 것.

## 스택 (안 A — 서버리스, 확정)
| 영역 | 선택 |
|---|---|
| 수집·분석 배치 | Python 3.12 (`collector/`), GitHub Actions cron |
| DB | Supabase Postgres + pgvector (`supabase/migrations/`) |
| 대시보드 | Next.js (App Router) on Vercel (`web/`) |
| LLM | Gemini API 무료 등급(Flash) 기본, 한도 초과(429) 시 Groq 무료 등급으로 전환 — 번역·묶기 판정·사실 추출·카드 생성. 요청은 묶어서 보내 호출 수 최소화 |
| 임베딩 | bge-m3 (오픈소스, 1024차원) — GitHub Actions에서 로컬 실행, 모델은 캐시. 예비: Gemini 임베딩(무료 분당 100문장) |
| 알림 | Telegram Bot + 메일(Resend 등) |

## 작업 원칙
1. **결정 체크포인트**: 기획서의 미정 항목에 걸리는 구현은 사용자에게 먼저 묻고 진행한다. Phase 경계마다 멈추고 결과를 보고한다.
2. **코딩 전 설계 확인**: 새 모듈은 인터페이스·테이블 영향을 먼저 짧게 제시하고 확인받는다.
3. 시간은 DB에 UTC로 저장, 화면·배치 기준은 KST.
4. 비밀값은 `.env` / GitHub Secrets / Vercel env에만. 커밋 금지.

## 법적·운영 가드레일 (절대 규칙)
- **기사 본문 전문 저장 금지.** 제목, 발행 시각, URL, 피드/API가 제공하는 요약만 저장.
- **유료벽 우회 금지.** 로그인 쿠키·우회 서비스·아카이브 미러 사용 금지.
- 이용 목적은 **PD 개인·비상업 용도**다 (연합뉴스·SBS RSS 조건 충족).
- robots.txt와 사이트 약관을 지킨다. 수집 간격은 피드(URL)당 최소 1시간, User-Agent에 연락처 명시. **User-Agent 위장 금지.**
- 수집 방식 우선순위: 공식 RSS → 매체가 robots.txt에 공개한 뉴스 사이트맵 → 공식 API → Google 뉴스 RSS(`gnews`) → 제외.
  - `gnews`는 `config/sources.yaml`에서 `method: gnews`로 지정된 매체에만 쓴다 (사유는 private/ 문서).
  - **네이버 뉴스 검색 API는 쓰지 않는다** (약관상 저장·AI 입력 금지).
  - **YouTube는 Data API만** 쓴다 (채널 RSS `/feeds/videos.xml`은 robots Disallow).
- HTML 스크래핑은 사용자 승인 없이 추가하지 않는다. 승인된 곳: 통계청 KOSIS 공표일정, 정책브리핑 일정 (하루 1회).
- **카드의 모든 사실 문장에는 근거 article_id가 1개 이상** 있어야 하며, 없으면 노출하지 않는다.
- "보도된 의혹" 상태는 단정 표현 금지("~했다" ✗ / "~라는 의혹이 보도됨" ✓). 당사자 반박이 있으면 같은 카드에 병기.
- 공인이 아닌 일반인(피의자·피해자 포함)은 기사에 실명이 있어도 사실·카드에 실명을 쓰지 않는다("A씨").
- 카드의 인물 후보: '기사 속 인물'은 근거 기사에 이름이 있어야 노출(코드 검증), 일반인 제외. 'AI 추천 인물'은 기사 근거가 없으므로 항상 "기사 근거 없음 · 확인 필요" 라벨과 함께만 보여 준다.
- 매체 성향 라벨은 시스템이 임의로 붙이지 않는다. `config/sources.yaml`의 `group`은 PD가 지정한다.
- 결과물은 내부용. 외부 공개 기능을 만들지 않는다.
- **이 저장소는 공개(public)다.** 특정 프로그램·코너·출연자·사용자를 짐작할 수 있는 이름이나 설명(코너 구성, 게스트 명단, 실명, 이메일, 텔레그램 chat id, Supabase·Vercel 주소)을 코드·설정·커밋·Actions 로그에 남기지 않는다.
- Actions 로그도 공개된다. 비밀값·개인정보·chat id를 print하지 않는다.

## 예약 실행
- GitHub `schedule`이 이 저장소에서 발화하지 않아(2026-11-15) **Supabase pg_cron → workflow_dispatch**로 깨운다 (`supabase/migrations/0005_dispatch_cron.sql`, 토큰은 Supabase Vault `github_actions_token`). 워크플로에 `schedule:`을 다시 넣지 말 것(중복 발송).
- 오후 업데이트 16:00·20:00 KST (`0006_update_cron.sql`, `morning-brief update`): 아침 이후 기사로 오늘 카드를 갱신하고 새 카드만 텔레그램 알림(메일 없음). 중간 결과(묶음·사실·새 사건)는 **내일 기준일**로 저장해 내일 아침 배치가 reset_day로 지우고 다시 계산한다 — 아침 브리핑의 '어제 대비 변화'를 바꾸지 않기 위함.

## GitHub Actions cron 주의
- cron은 UTC 기준이며 수 분~수십 분 지연될 수 있다 → 일일 배치는 05:30 KST(전날 20:30 UTC)에 시작해 07:30 SLA에 여유를 둔다.
- 각 단계는 타임아웃을 두고, 실패 시 부분 결과라도 저장·발송 + Telegram 실패 알림.

## 디렉터리
```
config/        sources.yaml, youtube_channels.yaml, ops.yaml, schedules.yaml
supabase/      migrations/*.sql
collector/     Python 패키지 (sources → pipeline → deliver)
web/           Next.js 대시보드 (Phase 1에서 create-next-app으로 생성)
.github/       workflows (collect: 매시간, daily: 05:30 KST)
private/       기획서·작업 목록 (로컬 전용, 커밋 금지)
```
