# morning-brief

국내외 매체 기사를 사건 단위로 묶고, 어제 대비 무엇이 달라졌는지를 정리해 매일 아침 브리핑(텔레그램·메일)과
대시보드로 전달하는 개인용·비상업 뉴스 정리 도구예요.

## 구성
```
config/      매체·유튜브 채널·운영 설정
supabase/    DB 마이그레이션 (Postgres + pgvector, pg_cron)
collector/   Python 수집·분석 배치 (morning-brief 명령)
web/         Next.js 대시보드 (로그인 필요)
.github/     GitHub Actions (Supabase pg_cron이 workflow_dispatch로 깨움)
```

## 원칙
- 기사 본문은 저장하지 않아요. 제목·발행 시각·URL·피드가 주는 요약만 저장해요.
- 공식 RSS·공개 사이트맵·공식 API만 쓰고, robots.txt와 약관을 지켜요. 유료벽 우회는 하지 않아요.
- 카드의 모든 사실에는 근거 기사가 있어야 하고, 일반인 실명은 쓰지 않아요.

## 로컬 실행
```bash
cd collector && uv venv --python 3.12 .venv && uv pip install -e ".[dev]"
cd .. && collector/.venv/bin/morning-brief collect --dry-run   # DB 없이 피드 점검
collector/.venv/bin/pytest -q collector/tests
```

비밀값(DB 주소, API 키, 봇 토큰 등)은 `.env`(로컬), GitHub Secrets, Vercel 환경 변수, Supabase Vault에만 둬요.
`.env.example`에 필요한 이름만 적혀 있어요.
