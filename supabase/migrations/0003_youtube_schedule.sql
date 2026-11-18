-- Phase 1-2: 유튜브 반응, 공식 일정

alter table schedule
  add column all_day boolean not null default false,
  add column kind    text,                    -- 국회: 본회의·위원회·국회행사 …
  add column place   text,
  add column host    text,
  add column fetched_at timestamptz not null default now();
create index on schedule (starts_at);

create index on yt_video (published_at desc);
create index on yt_video (channel_id, published_at desc);
