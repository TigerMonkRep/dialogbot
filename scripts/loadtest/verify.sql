-- Load-test verification (read-only). Was anything processed twice? Run against the TEMPORARY database only.
-- Calls of the load test carry provider_call_id 'loadtest-2026-11-13-<uuid>'.
with lt_calls as (select * from calls where provider_call_id like 'loadtest-2026-11-13-%')
select
  (select count(*) from lt_calls)                                                         as call_rows,
  (select count(distinct provider_call_id) from lt_calls)                                 as distinct_call_ids,
  (select count(*) from (select provider_call_id from lt_calls group by 1 having count(*) > 1) d) as calls_duplicated,
  (select count(*) from conversations c join lt_calls l on l.conversation_id = c.id)      as phone_conversations,
  (select count(*) from conversations where channel = 'phone'
      and workspace_id in (select workspace_id from lt_calls)
      and id not in (select conversation_id from lt_calls where conversation_id is not null)) as orphan_phone_conversations,
  (select count(*) from leads x join lt_calls l on l.conversation_id = x.conversation_id)  as leads,
  (select count(*) from (select x.conversation_id from leads x join lt_calls l on l.conversation_id = x.conversation_id
                         group by 1 having count(*) > 1) d)                                as leads_duplicated,
  (select count(*) from tasks t join leads x on x.id = t.lead_id join lt_calls l on l.conversation_id = x.conversation_id) as tasks,
  (select count(*) from webhook_events where provider = 'vapi' and event_id like 'loadtest-2026-11-13-%:end-of-call-report') as report_events,
  (select count(*) from (select event_id from webhook_events where provider = 'vapi' and event_id like 'loadtest-2026-11-13-%'
                         group by 1 having count(*) > 1) d)                                as report_events_duplicated,
  (select count(*) from outbox_events where status = 'done' and attempts > 1)             as outbox_done_after_retry,
  (select count(*) from outbox_events where status in ('failed','blocked'))               as outbox_failed_or_blocked,
  (select count(*) from outbox_events where status = 'queued')                            as outbox_still_queued,
  (select count(*) from (select dedupe_key from outbox_events group by 1 having count(*) > 1) d) as outbox_dedupe_dupes,
  (select count(*) from conversations where channel = 'webchat'
      and workspace_id in (select id from workspaces where slug like 'lt-%-loadtest-2026-11-13')) as webchat_conversations,
  (select count(*) from ai_usage where workspace_id in (select id from workspaces where slug like 'lt-%-loadtest-2026-11-13')) as ai_replies;
