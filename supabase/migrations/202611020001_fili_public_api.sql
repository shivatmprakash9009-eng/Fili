-- Fili public API storage. This schema is isolated from TIWAT tables.
create table if not exists public.fili_api_keys (
  id uuid primary key default gen_random_uuid(),
  owner_uid text not null,
  name text not null check (char_length(name) between 2 and 80),
  key_prefix text not null,
  key_hash text not null unique,
  scopes text[] not null default array['prospects:read','prospects:write']::text[],
  last_used_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists fili_api_keys_owner_created_idx
  on public.fili_api_keys (owner_uid, created_at desc);
create index if not exists fili_api_keys_active_prefix_idx
  on public.fili_api_keys (key_prefix) where revoked_at is null;

create table if not exists public.fili_prospects (
  id uuid primary key default gen_random_uuid(),
  owner_uid text not null,
  source_type text not null,
  source_id text not null default '',
  company_name text not null,
  website text not null default '',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_uid, source_type, source_id)
);

create index if not exists fili_prospects_owner_created_idx
  on public.fili_prospects (owner_uid, created_at desc);
create index if not exists fili_prospects_owner_name_idx
  on public.fili_prospects (owner_uid, company_name);

create table if not exists public.fili_api_usage (
  id bigint generated always as identity primary key,
  api_key_id uuid not null references public.fili_api_keys(id) on delete cascade,
  owner_uid text not null,
  route text not null,
  status_code integer not null check (status_code between 100 and 599),
  created_at timestamptz not null default now()
);

create index if not exists fili_api_usage_owner_created_idx
  on public.fili_api_usage (owner_uid, created_at desc);
create index if not exists fili_api_usage_key_created_idx
  on public.fili_api_usage (api_key_id, created_at desc);

-- Service role is the only database principal used by the API service.
-- Enable RLS and deliberately provide no anon/authenticated policies.
alter table public.fili_api_keys enable row level security;
alter table public.fili_prospects enable row level security;
alter table public.fili_api_usage enable row level security;

revoke all on public.fili_api_keys from anon, authenticated;
revoke all on public.fili_prospects from anon, authenticated;
revoke all on public.fili_api_usage from anon, authenticated;
grant all on public.fili_api_keys to service_role;
grant all on public.fili_prospects to service_role;
grant all on public.fili_api_usage to service_role;
grant usage, select on sequence public.fili_api_usage_id_seq to service_role;
