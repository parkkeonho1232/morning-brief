-- GitHub 예약(schedule)이 돌지 않아 Supabase pg_cron이 workflow_dispatch로 깨운다 (2026-11-16 결정).
-- 토큰은 Supabase Vault의 'github_actions_token' (fine-grained PAT, 이 저장소 Actions: Read and write).
-- pg_cron은 UTC 기준.

create extension if not exists pg_cron;
create extension if not exists pg_net with schema extensions;

create or replace function public.dispatch_workflow(workflow text, inputs jsonb default '{}'::jsonb)
returns bigint
language sql
security definer
set search_path = public, extensions
as $$
  select net.http_post(
    url := 'https://api.github.com/repos/parkkeonho1232/morning-brief/actions/workflows/' || workflow || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets
                                     where name = 'github_actions_token' limit 1),
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'morning-brief-cron',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'master', 'inputs', inputs)
  );
$$;

revoke all on function public.dispatch_workflow(text, jsonb) from public, anon, authenticated;

-- 매시 12분: 수집
select cron.schedule('brief-collect', '12 * * * *',
                     $$select public.dispatch_workflow('collect.yml')$$);
-- 20:30 UTC = 05:30 KST: 일일 배치 + 텔레그램 발송
select cron.schedule('brief-daily', '30 20 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"send": "true"}'::jsonb)$$);
