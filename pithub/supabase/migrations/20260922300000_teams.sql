-- pithub: 팀 운용 — 초대는 본인이 수락한다, 팀·친구가 읽는 열은 공개 뷰와 같다 (D-0008)
--
-- 남의 결정 원장에 내 이름이 동의 없이 오르면 안 된다. 구성원 행은 소유자가 만들지만
-- accepted_at 은 초대받은 본인만 채운다. 수락 전에는 팀의 어떤 결정도 보이지 않는다.
--
-- decisions 의 행 정책은 열을 가리지 못한다. 팀원·친구가 decisions 를 직접 읽으면 source(세션 id 등)까지
-- 보이므로, 그 두 정책을 지우고 공개 뷰처럼 열을 고른 뷰로만 읽게 한다.

-- ---------------------------------------------------------------------------
-- 초대 · 수락
-- ---------------------------------------------------------------------------

alter table public.team_members
    add column invited_by bigint references public.accounts (github_id) on delete set null,
    add column accepted_at timestamptz;

-- 이 마이그레이션 전의 구성원은 모두 수락된 것으로 본다
update public.team_members set accepted_at = joined_at;

-- 팀을 만든 사람이 계정을 지워도 팀은 남는다 (구성원의 결정이 거기 있다)
alter table public.teams alter column created_by drop not null;
alter table public.teams drop constraint teams_created_by_fkey;
alter table public.teams add constraint teams_created_by_fkey
    foreign key (created_by) references public.accounts (github_id) on delete set null;

create or replace function public.is_team_member(team uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.team_members
        where team_id = team and github_id = public.current_github_id() and accepted_at is not null
    )
$$;

create function public.has_team_invite(team uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.team_members
        where team_id = team and github_id = public.current_github_id() and accepted_at is null
    )
$$;

create function public.is_team_owner(team uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.team_members
        where team_id = team and github_id = public.current_github_id()
          and role = 'owner' and accepted_at is not null
    )
$$;

-- 같은 팀에 얽힌 사람인가 (초대 중인 사람 포함 — 초대장에 보낸 사람 이름이 보여야 한다)
create function public.shares_team_with(other bigint) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.team_members mine
        join public.team_members theirs on theirs.team_id = mine.team_id
        where mine.github_id = public.current_github_id() and theirs.github_id = other
    )
$$;

-- 팀 만들기: 팀과 소유자 행을 한 번에. 소유자는 스스로를 초대할 필요가 없다.
create function public.create_team(team_slug text, team_name text) returns uuid
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    new_id uuid;
begin
    if me is null then
        raise exception 'not signed in' using errcode = 'insufficient_privilege';
    end if;
    insert into public.teams (slug, name, created_by) values (team_slug, team_name, me) returning id into new_id;
    insert into public.team_members (team_id, github_id, role, invited_by, accepted_at)
        values (new_id, me, 'owner', me, now());
    return new_id;
end
$$;

-- 초대: 계정 목록을 노출하지 않고 로그인 이름으로 찾는다. 팀 소유자만.
create function public.invite_to_team(team uuid, login text) returns void
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    target bigint;
begin
    if not public.is_team_owner(team) then
        raise exception 'not a team owner' using errcode = 'insufficient_privilege';
    end if;
    select github_id into target from public.accounts where github_login = login;
    if target is null then
        raise exception 'no pithub account for %', login using errcode = 'no_data_found';
    end if;
    insert into public.team_members (team_id, github_id, role, invited_by)
        values (team, target, 'member', me)
        on conflict (team_id, github_id) do nothing;
end
$$;

revoke all on function public.create_team(text, text), public.invite_to_team(uuid, text) from public;
grant execute on function public.create_team(text, text), public.invite_to_team(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- 접근 권한
-- ---------------------------------------------------------------------------

-- 초대받은 사람은 팀 이름을 봐야 수락할 수 있다
drop policy teams_select_member on public.teams;
create policy teams_select_member_or_invited on public.teams
    for select to authenticated using (public.is_team_member(id) or public.has_team_invite(id));
-- 팀은 create_team() 으로만 만든다
drop policy teams_insert_self on public.teams;
revoke insert on public.teams from authenticated;

drop policy team_members_select_member on public.team_members;
create policy team_members_select_member_or_self on public.team_members
    for select to authenticated
    using (public.is_team_member(team_id) or github_id = (select public.current_github_id()));

-- 구성원 행은 invite_to_team() · create_team() 으로만 생긴다
drop policy team_members_insert_owner on public.team_members;
revoke insert on public.team_members from authenticated;

-- 수락은 초대받은 본인만, accepted_at 열만
grant update (accepted_at) on public.team_members to authenticated;
create policy team_members_accept_self on public.team_members
    for update to authenticated
    using (github_id = (select public.current_github_id()) and accepted_at is null)
    with check (github_id = (select public.current_github_id()));

-- 거절·탈퇴는 본인, 내보내기는 소유자 (기존 정책을 함수로 다시 쓴다)
drop policy team_members_delete_self_or_owner on public.team_members;
create policy team_members_delete_self_or_owner on public.team_members
    for delete to authenticated
    using (github_id = (select public.current_github_id()) or public.is_team_owner(team_id));

-- 팀원(초대 중 포함)의 로그인 이름·아바타는 서로 본다
create policy accounts_select_teammate on public.accounts
    for select to authenticated using (public.shares_team_with(github_id));

-- ---------------------------------------------------------------------------
-- 팀 · 친구가 읽는 뷰 — 공개 뷰와 같은 열, 출처·가림 내역 없음
-- ---------------------------------------------------------------------------

drop policy decisions_select_team on public.decisions;
drop policy decisions_select_friends on public.decisions;

create view public.team_decisions
with (security_invoker = false)
as
select
    d.id, d.owner_github_id, a.github_login, a.avatar_url, d.team_id, t.slug as team_slug,
    d.kind, d.verdict, d.reject_kind, d.situation, d.proposal, d.options, d.chosen, d.rationale,
    d.human_quote, d.tags, d.supersedes, d.consulted, d.decided_at, d.cited_count
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
join public.teams t on t.id = d.team_id
where d.status = 'confirmed' and d.visibility = 'team' and public.is_team_member(d.team_id);

create view public.friends_decisions
with (security_invoker = false)
as
select
    d.id, d.owner_github_id, a.github_login, a.avatar_url,
    d.kind, d.verdict, d.reject_kind, d.situation, d.proposal, d.options, d.chosen, d.rationale,
    d.human_quote, d.tags, d.supersedes, d.consulted, d.decided_at
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
where d.status = 'confirmed' and d.visibility = 'friends' and public.are_friends(d.owner_github_id);

grant select on public.team_decisions, public.friends_decisions to authenticated;
