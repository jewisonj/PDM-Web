-- Shop Notes: quick issue notes + photos from shop-floor phones (Shop Companion)
--
-- Apply in the Supabase SQL editor (or via MCP). Backend accesses these tables
-- with the service-role key, so RLS is enabled with no anon policies.

-- Private bucket for note photos (served through backend signed URLs)
insert into storage.buckets (id, name, public)
values ('shop-note-photos', 'shop-note-photos', false)
on conflict (id) do nothing;

create table if not exists public.shop_notes (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.mrp_projects(id) on delete set null,
  assembly_item_id uuid references public.items(id) on delete set null,
  part_item_id uuid references public.items(id) on delete set null,
  -- Free text the worker typed when it did not match a BOM item (reviewer can fix later)
  assembly_text text,
  part_text text,
  note text not null default '',
  author_name text,
  status text not null default 'new' check (status in ('new', 'reviewed', 'resolved')),
  reviewer_notes text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_shop_notes_status_created on public.shop_notes(status, created_at desc);
create index if not exists idx_shop_notes_project on public.shop_notes(project_id);
create index if not exists idx_shop_notes_part on public.shop_notes(part_item_id);

create table if not exists public.shop_note_photos (
  id uuid primary key default gen_random_uuid(),
  note_id uuid not null references public.shop_notes(id) on delete cascade,
  file_path text not null,          -- "<bucket>/<path>" like design_book_images
  file_size bigint,
  mime_type text,
  sort_order int not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_shop_note_photos_note on public.shop_note_photos(note_id);

create or replace function public.update_shop_notes_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_shop_notes_updated_at on public.shop_notes;
create trigger trg_shop_notes_updated_at
  before update on public.shop_notes
  for each row execute function public.update_shop_notes_updated_at();

alter table public.shop_notes enable row level security;
alter table public.shop_note_photos enable row level security;
