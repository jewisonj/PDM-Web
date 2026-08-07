-- Shared links feature (applied to Supabase 2026-08-07 via MCP)
--
-- Public bucket for deliberately-shared documents. public=true means objects
-- are served at a permanent URL with no auth and no expiry:
--   {SUPABASE_URL}/storage/v1/object/public/shared/{path}
-- Sharing = knowing the link; revoking = deleting the object.
--
-- NOTE: uploads into this bucket (like all buckets) are capped by the
-- project-wide upload size limit (Dashboard -> Project Settings -> Storage).
-- Per-bucket file_size_limit values above the global cap have no effect.

insert into storage.buckets (id, name, public, file_size_limit)
values ('shared', 'shared', true, null)
on conflict (id) do update set public = true;

create table if not exists public.shared_links (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('build_book', 'tracker', 'print_packet', 'design_book', 'other')),
  project_code text,
  title text not null,
  file_name text not null,
  storage_path text not null unique,
  public_url text not null,
  size_bytes bigint,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_shared_links_project on public.shared_links(project_code);

alter table public.shared_links enable row level security;
