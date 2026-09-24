-- Supabase가 제공하는 것 중 RLS 검증에 필요한 최소한만 흉내 낸다.
-- 실제 Supabase와 같은 이름의 역할 · auth 스키마 · auth.uid() 를 만든다.

do $$
begin
    if not exists (select from pg_roles where rolname = 'anon') then create role anon nologin; end if;
    if not exists (select from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
    if not exists (select from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;

drop schema if exists public cascade;
drop schema if exists auth cascade;
create schema public;
create schema auth;
grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to service_role;
-- identity 열(bigint generated always)의 시퀀스 — 서버(service_role)가 PostgREST로 행을 넣을 때 필요하다
alter default privileges in schema public grant usage, select on sequences to service_role;

create table auth.users (
    id uuid primary key,
    raw_user_meta_data jsonb not null default '{}'::jsonb
);

create table auth.identities (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    provider text not null,
    provider_id text not null,
    identity_data jsonb not null default '{}'::jsonb
);

-- Supabase의 auth.uid()와 같은 동작: 요청 JWT의 sub를 읽는다
create function auth.uid() returns uuid
language sql stable
as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
