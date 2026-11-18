-- 아침 브리핑 툴 초기 스키마
-- 원칙: 기사 본문 저장 컬럼 없음. 시간은 timestamptz(UTC).

create extension if not exists vector;

create table source (
  id            bigserial primary key,
  name          text not null unique,
  region        text not null check (region in ('domestic','international')),
  lang          text not null default 'ko',
  grp           text,                         -- PD 지정 그룹
  method        text check (method in ('rss','sitemap','gnews','api','none')),
  feed_url      text,
  paywall       boolean not null default false,
  active        boolean not null default true,
  last_ok_at    timestamptz
);

create table article (
  id            bigserial primary key,
  source_id     bigint not null references source(id),
  url           text not null unique,
  title         text not null,
  title_ko      text,
  summary       text,                         -- 피드/API 제공 요약만
  summary_ko    text,
  published_at  timestamptz not null,
  collected_at  timestamptz not null default now(),
  embedding     vector(1024),                 -- 차원은 임베딩 모델 확정 후 조정
  cluster_id    bigint
);
create index on article (published_at desc);
create index on article (cluster_id);

create table event (
  id                bigserial primary key,
  title             text not null,            -- 중립 표현
  first_seen_date   date not null,
  last_change_date  date,
  status            text not null default 'active',
  verification      text not null default '확인 대기'
                    check (verification in ('공식 확인','보도된 의혹','당사자 반박','확인 대기'))
);

create table event_fact (
  id              bigserial primary key,
  event_id        bigint not null references event(id) on delete cascade,
  fact            text not null,
  change_type     text not null check (change_type in
                  ('최초 보도','당사자 해명','인정','반박 자료','공식 조치','확장','수치 변경')),
  first_seen_date date not null,
  article_ids     bigint[] not null check (cardinality(article_ids) >= 1)  -- 근거 필수
);

create table event_snapshot (
  event_id    bigint not null references event(id) on delete cascade,
  base_date   date not null,
  facts_hash  text not null,
  score       numeric,
  primary key (event_id, base_date)
);

create table yt_channel (
  id            text primary key,             -- YouTube channel id
  handle        text,
  name          text,
  baseline_6h   numeric,
  baseline_24h  numeric,
  active        boolean not null default true
);

create table yt_video (
  id            text primary key,
  channel_id    text not null references yt_channel(id),
  title         text not null,
  published_at  timestamptz not null,
  event_id      bigint references event(id)
);

create table yt_stat (
  video_id    text not null references yt_video(id) on delete cascade,
  captured_at timestamptz not null,
  views       bigint not null,
  primary key (video_id, captured_at)
);

create table schedule (
  id          bigserial primary key,
  org         text not null,                  -- 국회, 한국은행, 통계청, 정책브리핑 ...
  title       text not null,
  starts_at   timestamptz not null,
  url         text,
  unique (org, title, starts_at)
);

create table card (
  id          bigserial primary key,
  base_date   date not null,
  event_id    bigint references event(id),
  rank        int not null,
  kind        text not null check (kind in ('top','extension')),
  body        jsonb not null,                 -- 카드 전체 항목
  memo        text,
  decision    text check (decision in ('채택','보류')),
  unique (base_date, kind, rank)
);

create table run_log (
  id          bigserial primary key,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  job         text not null,                  -- collect | daily
  step        text,
  ok          boolean,
  detail      jsonb,
  cost_usd    numeric
);
