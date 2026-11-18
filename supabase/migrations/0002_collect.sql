-- Phase 1-1 수집기: 피드별 상태, 설정 동기화 컬럼, 기사 중복 제거 키

-- 한 매체가 섹션 피드 여러 개를 쓸 수 있도록 목록으로
alter table source drop column feed_url;
alter table source
  add column feed_urls   text[]  not null default '{}',
  add column has_summary boolean not null default true,
  add column tz_naive    boolean not null default false;
alter table source drop constraint source_method_check;
alter table source add constraint source_method_check
  check (method in ('rss','sitemap','gnews','api','none'));

alter table article
  add column lang        text not null default 'ko',
  add column via         text not null default 'rss' check (via in ('rss','sitemap','gnews','api')),
  add column title_hash  text not null default '';
create index on article (source_id, title_hash);

-- 피드(URL)별 수집 상태: 1시간 간격 준수, 조건부 요청, 누락·중단 감지
create table feed_state (
  feed_url              text primary key,
  source_id             bigint not null references source(id) on delete cascade,
  etag                  text,
  last_modified         text,
  last_fetch_at         timestamptz,
  last_ok_at            timestamptz,
  last_item_count       int,
  newest_published_at   timestamptz,
  consecutive_failures  int not null default 0,
  last_error            text,
  baseline_urls         text[] not null default '{}'   -- 첫 수집 때 이미 있던 발행시각 없는 기사 (백필 방지)
);

alter table yt_channel
  add column kind        text not null default 'sisa' check (kind in ('sisa','news')),
  add column source_name text;                -- news 채널이 대응하는 매체

-- 수집 시작 시각 등 단일 값
create table app_meta (
  key    text primary key,
  value  text not null
);
