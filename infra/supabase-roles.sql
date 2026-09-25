-- Run once per Supabase project (SQL editor) BEFORE the first `alembic upgrade head`.
-- Two roles: a migration owner and a limited runtime role for API + worker.
-- Replace the passwords via the dashboard; do not commit real values.

create schema if not exists dialogbot;

create role dialogbot_migrate login password 'CHANGE_ME_MIGRATE';
create role dialogbot_app     login password 'CHANGE_ME_APP';

grant usage, create on schema dialogbot to dialogbot_migrate;
alter schema dialogbot owner to dialogbot_migrate;
grant usage on schema dialogbot to dialogbot_app;

-- Runtime may read/write application tables but never alter them.
alter default privileges for role dialogbot_migrate in schema dialogbot
  grant select, insert, update, delete on tables to dialogbot_app;
alter default privileges for role dialogbot_migrate in schema dialogbot
  grant usage, select on sequences to dialogbot_app;

-- Keep the application schema out of the auto-generated Data API (PostgREST):
-- Dashboard → Settings → API → "Exposed schemas" must NOT include `dialogbot`.
-- Both roles connect with `options=-csearch_path=dialogbot`.
