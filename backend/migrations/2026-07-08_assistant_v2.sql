-- Assistant v2 migrations (applied to Supabase 2026-07-08 via MCP)
-- 1. Persistent conversation storage
-- 2. Guarded read-only SQL execution (assistant_query)

-- ============================================================
-- 1. Conversation persistence
-- ============================================================

create table if not exists public.assistant_conversations (
  id uuid primary key default gen_random_uuid(),
  title text,
  page_context text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.assistant_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.assistant_conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content jsonb not null,
  hidden boolean not null default false,  -- tool results / action outcome notes: kept for the model, not shown in UI
  created_at timestamptz not null default now()
);

create index if not exists idx_assistant_messages_conversation
  on public.assistant_messages(conversation_id, created_at);

create index if not exists idx_assistant_conversations_updated
  on public.assistant_conversations(updated_at desc);

alter table public.assistant_conversations enable row level security;
alter table public.assistant_messages enable row level security;

-- ============================================================
-- 2. Read-only SQL execution
-- ============================================================
-- assistant_readonly owns the security-definer function, so queries run
-- with SELECT-only privileges: even if a query sneaks past application-level
-- filtering, writes fail at the permission layer. (SET ROLE inside a
-- security-definer function is disallowed by Postgres, hence ownership.)

do $$
begin
  if not exists (select from pg_roles where rolname = 'assistant_readonly') then
    create role assistant_readonly nologin;
  end if;
end $$;

grant usage on schema public to assistant_readonly;
grant select on all tables in schema public to assistant_readonly;
alter default privileges in schema public grant select on tables to assistant_readonly;

create or replace function public.assistant_query(sql text, max_rows integer default 200)
returns jsonb
language plpgsql
security definer
set search_path = public
set statement_timeout = '5000ms'
as $$
declare
  result jsonb;
begin
  if sql !~* '^\s*(select|with)\M' then
    raise exception 'Only SELECT queries are allowed';
  end if;
  if position(';' in rtrim(sql, '; ')) > 0 then
    raise exception 'Multiple statements are not allowed';
  end if;
  if max_rows is null or max_rows < 1 or max_rows > 500 then
    max_rows := 200;
  end if;

  execute format(
    'select coalesce(jsonb_agg(t), ''[]''::jsonb) from (select * from (%s) q limit %s) t',
    rtrim(sql, '; '), max_rows
  ) into result;

  return result;
end;
$$;

grant assistant_readonly to postgres;  -- required to transfer ownership
grant create on schema public to assistant_readonly;
alter function public.assistant_query(text, integer) owner to assistant_readonly;
revoke create on schema public from assistant_readonly;

revoke execute on function public.assistant_query(text, integer) from public;
revoke execute on function public.assistant_query(text, integer) from anon;
revoke execute on function public.assistant_query(text, integer) from authenticated;
grant execute on function public.assistant_query(text, integer) to service_role;
