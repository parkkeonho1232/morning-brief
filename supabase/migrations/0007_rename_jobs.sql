-- 저장소 이름 변경(morning-brief)에 맞춰 예약 작업과 호출 주소를 다시 만든다.
select cron.unschedule(jobid) from cron.job where command like '%dispatch_workflow%';

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

select cron.schedule('brief-collect', '12 * * * *',
                     $$select public.dispatch_workflow('collect.yml')$$);
select cron.schedule('brief-daily', '30 20 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"send": "true"}'::jsonb)$$);
select cron.schedule('brief-update-16', '0 7 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"update": "true", "send": "true"}'::jsonb)$$);
select cron.schedule('brief-update-20', '0 11 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"update": "true", "send": "true"}'::jsonb)$$);
