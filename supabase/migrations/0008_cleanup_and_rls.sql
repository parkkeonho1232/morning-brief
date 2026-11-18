-- 쓰지 않는 칸 정리 + 모든 테이블에 RLS를 켠다.
-- 이 도구는 서버(DATABASE_URL, 테이블 소유자)로만 DB에 접근한다. RLS는 소유자에게는 적용되지 않으므로 동작은 그대로이고,
-- Supabase 공개 REST API(anon·authenticated 키)로는 어떤 행도 읽거나 쓸 수 없게 된다 (정책을 만들지 않음).
alter table card drop column if exists corner, drop column if exists alt_corner;

do $$
begin
  if exists (select 1 from information_schema.columns where table_name = 'card' and column_name = 'pd_memo') then
    alter table card rename column pd_memo to memo;
  end if;
  if exists (select 1 from information_schema.columns where table_name = 'card' and column_name = 'pd_decision') then
    alter table card rename column pd_decision to decision;
  end if;
end $$;

do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end $$;
