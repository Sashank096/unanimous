begin;

alter table public.profile
  add column if not exists profile_image_public_url text;

update public.profile
set profile_image_public_url =
  'https://ruewkkyeynnfgkhoabzu.supabase.co/storage/v1/object/public/profile-images/'
  || profile_image_url
where nullif(profile_image_url, '') is not null;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'profile-images',
  'profile-images',
  true,
  5242880,
  array['image/png', 'image/jpeg', 'image/webp']
)
on conflict (id) do update
set public = true,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

commit;
