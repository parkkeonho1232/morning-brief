-- 오후 업데이트 (2026-11-18 결정): 16:00·20:00 KST에 아침 이후 기사로 오늘 카드를 갱신하고 새 카드만 텔레그램 알림.
-- 07:00 UTC = 16:00 KST, 11:00 UTC = 20:00 KST
select cron.schedule('brief-update-16', '0 7 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"update": "true", "send": "true"}'::jsonb)$$);
select cron.schedule('brief-update-20', '0 11 * * *',
                     $$select public.dispatch_workflow('daily.yml', '{"update": "true", "send": "true"}'::jsonb)$$);
