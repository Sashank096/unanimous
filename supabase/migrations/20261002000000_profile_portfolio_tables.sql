begin;

create table if not exists public.profile (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  full_name text not null default '',
  email text,
  headline text not null default '',
  bio text not null default '',
  mobile_number text not null default '',
  location text not null default '',
  profile_image_url text,
  profile_image_public boolean not null default false,
  public_slug text not null unique,
  portfolio_published boolean not null default false,
  portfolio_theme text not null default 'studio',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profile
  add column if not exists user_id uuid references auth.users(id) on delete cascade,
  add column if not exists full_name text not null default '',
  add column if not exists email text,
  add column if not exists headline text not null default '',
  add column if not exists bio text not null default '',
  add column if not exists mobile_number text not null default '',
  add column if not exists location text not null default '',
  add column if not exists profile_image_url text,
  add column if not exists profile_image_public boolean not null default false,
  add column if not exists public_slug text,
  add column if not exists portfolio_published boolean not null default false,
  add column if not exists portfolio_theme text not null default 'studio',
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists updated_at timestamptz not null default now();

update public.profile
set public_slug = trim(both '-' from regexp_replace(
  lower(coalesce(nullif(full_name, ''), nullif(email, ''), 'portfolio')),
  '[^a-z0-9]+', '-', 'g'
)) || '-' || left(user_id::text, 8)
where public_slug is null and user_id is not null;

alter table public.profile alter column public_slug set not null;
create unique index if not exists profile_user_id_uidx on public.profile (user_id);
create unique index if not exists profile_public_slug_uidx on public.profile (public_slug);

create table if not exists public.profile_links (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profile(id) on delete cascade,
  platform_name text not null,
  url text not null check (url ~ '^https?://'),
  display_order integer not null default 0,
  created_at timestamptz not null default now()
);

alter table public.profile_links
  add column if not exists profile_id uuid references public.profile(id) on delete cascade,
  add column if not exists platform_name text not null default 'Other',
  add column if not exists url text not null default '',
  add column if not exists display_order integer not null default 0,
  add column if not exists created_at timestamptz not null default now();

create index if not exists profile_links_profile_order_idx
  on public.profile_links (profile_id, display_order);

alter table public.profile enable row level security;
alter table public.profile_links enable row level security;

drop policy if exists "profile owner can read and manage own profile" on public.profile;
create policy "profile owner can read and manage own profile"
  on public.profile for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "published profiles are publicly readable" on public.profile;
create policy "published profiles are publicly readable"
  on public.profile for select to anon, authenticated
  using (portfolio_published is true);

drop policy if exists "profile owners can manage own links" on public.profile_links;
create policy "profile owners can manage own links"
  on public.profile_links for all to authenticated
  using (
    exists (
      select 1 from public.profile p
      where p.id = profile_id and p.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.profile p
      where p.id = profile_id and p.user_id = (select auth.uid())
    )
  );

drop policy if exists "published profile links are publicly readable" on public.profile_links;
create policy "published profile links are publicly readable"
  on public.profile_links for select to anon, authenticated
  using (
    exists (
      select 1 from public.profile p
      where p.id = profile_id and p.portfolio_published is true
    )
  );

grant select, insert, update, delete on public.profile to authenticated;
grant select on public.profile to anon;
grant select, insert, update, delete on public.profile_links to authenticated;
grant select on public.profile_links to anon;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'profile-images',
  'profile-images',
  false,
  5242880,
  array['image/png', 'image/jpeg', 'image/webp']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "profile owners can read own photo" on storage.objects;
create policy "profile owners can read own photo"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'profile-images'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "published profile photos are readable" on storage.objects;
create policy "published profile photos are readable"
  on storage.objects for select to anon, authenticated
  using (
    bucket_id = 'profile-images'
    and exists (
      select 1 from public.profile p
      where p.user_id::text = (storage.foldername(name))[1]
        and p.profile_image_url = name
        and p.profile_image_public is true
        and p.portfolio_published is true
    )
  );

drop policy if exists "profile owners can upload own photo" on storage.objects;
create policy "profile owners can upload own photo"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'profile-images'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "profile owners can update own photo" on storage.objects;
create policy "profile owners can update own photo"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'profile-images'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'profile-images'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "profile owners can delete own photo" on storage.objects;
create policy "profile owners can delete own photo"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'profile-images'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

commit;
