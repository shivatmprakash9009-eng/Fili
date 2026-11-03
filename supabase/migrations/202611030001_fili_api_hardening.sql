-- Fili API hardening: keep prospects.updated_at accurate and speed up usage/quota queries.

create or replace function public.fili_touch_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists fili_prospects_touch_updated_at on public.fili_prospects;
create trigger fili_prospects_touch_updated_at
  before update on public.fili_prospects
  for each row execute function public.fili_touch_updated_at();

-- Daily search quota counts rows by owner + route + day.
create index if not exists fili_api_usage_owner_route_created_idx
  on public.fili_api_usage (owner_uid, route, created_at desc);

-- Retire the unused prefix index (lookups use the unique key_hash index).
drop index if exists public.fili_api_keys_active_prefix_idx;
