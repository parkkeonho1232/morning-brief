-- Phase 1-3: 기사 묶음(cluster), 사건 연결, 변화 감지

create table cluster (
  id            bigserial primary key,
  base_date     date not null,                 -- 집계 기준일 (전일 05:30 ~ 당일 05:30 KST)
  article_ids   bigint[] not null,
  n_articles    int not null,
  n_sources     int not null,                  -- 독립 매체 수 (같은 매체 여러 건은 1)
  n_wire        int not null default 0,        -- 통신사 기사 수 (받아쓰기 원천)
  has_intl      boolean not null default false,
  has_domestic  boolean not null default false,
  embed_model   text not null,
  event_id      bigint references event(id) on delete set null,
  link_method   text check (link_method in ('new','auto','llm')),
  created_at    timestamptz not null default now()
);
create index on cluster (base_date);
create index on cluster (event_id);

-- 고위험 변화 유형(인정·반박 자료)은 자동 판정 표시
alter table event_fact add column needs_review boolean not null default false;
create index on event_fact (event_id, first_seen_date);
create index on event (last_change_date desc);
