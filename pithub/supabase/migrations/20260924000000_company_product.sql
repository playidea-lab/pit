-- pithub: 회사가 사는 제품으로 (D-0010)
--
-- 1. 공개·친구 범위를 걷어낸다. 회사 판단이 밖으로 나가는 경로를 코드에 남기지 않는다.
-- 2. 팀 범위 초안은 기록 3일 뒤 자동으로 팀에 보인다. 그 전에 본인이 빼거나(private) 버릴 수 있다 — 사후 거부.
-- 3. 팀에 보이게 된 판단은 회사의 기록이다. 본인이 계정을 지워도 남고, 팀 소유자만 지운다(erase_member_persona).

-- ---------------------------------------------------------------------------
-- 1. 공개 · 친구 제거
-- ---------------------------------------------------------------------------

drop view if exists public.public_decisions;
drop view if exists public.friends_decisions;
drop function if exists public.are_friends(bigint);
drop table if exists public.follows;

update public.decisions set visibility = 'private', team_id = null where visibility in ('public', 'friends');
alter table public.decisions drop constraint decisions_visibility_check;
alter table public.decisions add constraint decisions_visibility_check check (visibility in ('private', 'team'));

delete from public.project_defaults where visibility in ('public', 'friends');
alter table public.project_defaults drop constraint project_defaults_visibility_check;
alter table public.project_defaults add constraint project_defaults_visibility_check check (visibility in ('private', 'team'));

-- ---------------------------------------------------------------------------
-- 2. 3일 뒤 자동 공유
-- ---------------------------------------------------------------------------

-- 서버(pit/server/tools.py)와 웹(lib/decisions.ts)의 TEAM_SHARE_GRACE 와 같은 값이어야 한다.
create function public.team_share_grace() returns interval
language sql immutable
as $$ select interval '3 days' $$;

-- 팀에 보이는가: 팀 범위이고, 확인됐거나 유예 기간이 지났고, 버리지 않았다
create function public.is_team_shared(visibility text, status text, created_at timestamptz) returns boolean
language sql stable
as $$
    select visibility = 'team' and status <> 'discarded'
       and (status = 'confirmed' or created_at <= now() - public.team_share_grace())
$$;

-- 팀에 보이게 된 판단은 본인도 팀에서 빼거나 버리거나 지우지 못한다 (회사의 기록). 글 고치기와 확인은 된다.
create function public.guard_shared_decision() returns trigger
language plpgsql
as $$
begin
    if current_user = 'authenticated'
       and public.is_team_shared(old.visibility, old.status, old.created_at)
       and (new.visibility <> old.visibility or new.team_id is distinct from old.team_id or new.status = 'discarded') then
        raise exception 'shared with the team — only the team owner can remove it' using errcode = 'insufficient_privilege';
    end if;
    return new;
end
$$;

create trigger decisions_guard_shared
    before update on public.decisions
    for each row execute function public.guard_shared_decision();

drop policy decisions_delete_own on public.decisions;
create policy decisions_delete_own_unshared on public.decisions
    for delete to authenticated
    using (owner_github_id = (select public.current_github_id())
        and not public.is_team_shared(visibility, status, created_at));

-- ---------------------------------------------------------------------------
-- 3. 팀 뷰 — 확인됐거나 유예가 지난 것, 떠난 사람 표시
-- ---------------------------------------------------------------------------

alter table public.accounts add column deleted_at timestamptz;

drop view public.team_decisions;
create view public.team_decisions
with (security_invoker = false)
as
select
    d.id, d.owner_github_id, a.github_login, a.avatar_url, a.deleted_at is not null as departed,
    d.team_id, t.slug as team_slug, d.status = 'confirmed' as verified,
    d.kind, d.verdict, d.reject_kind, d.situation, d.proposal, d.options, d.chosen, d.rationale,
    d.human_quote, d.tags, d.supersedes, d.consulted, d.decided_at, d.cited_count
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
join public.teams t on t.id = d.team_id
where public.is_team_shared(d.visibility, d.status, d.created_at) and public.is_team_member(d.team_id);

grant select on public.team_decisions to authenticated;

-- ---------------------------------------------------------------------------
-- 4. 계정 삭제 — 내 것은 사라지고, 팀에 보이게 된 것은 남는다
-- ---------------------------------------------------------------------------

create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
begin
    if me is null then
        raise exception 'not signed in' using errcode = '28000';
    end if;
    delete from public.decisions
     where owner_github_id = me and not public.is_team_shared(visibility, status, created_at);
    delete from public.api_tokens where owner_github_id = me;
    delete from public.review_events where owner_github_id = me;
    delete from public.citations where owner_github_id = me;
    delete from public.team_members where github_id = me;

    if exists (select 1 from public.decisions where owner_github_id = me) then
        -- 작성자 표시를 위해 계정 행만 남기고 로그인 연결을 끊는다
        update public.accounts set deleted_at = now() where github_id = me;
        delete from public.profiles where github_id = me;
    else
        delete from public.accounts where github_id = me;
    end if;
end;
$$;

-- 팀 소유자만: 한 사람이 이 팀에 남긴 판단을 전부 지운다 (퇴사자 페르소나 삭제)
create function public.erase_member_persona(team uuid, member bigint) returns integer
language plpgsql security definer set search_path = ''
as $$
declare
    erased integer;
begin
    if not public.is_team_owner(team) then
        raise exception 'not a team owner' using errcode = 'insufficient_privilege';
    end if;
    delete from public.decisions where owner_github_id = member and team_id = team;
    get diagnostics erased = row_count;
    -- 떠난 사람이고 더 남은 것이 없으면 계정 행도 지운다
    delete from public.accounts a
     where a.github_id = member and a.deleted_at is not null
       and not exists (select 1 from public.decisions d where d.owner_github_id = member);
    return erased;
end;
$$;

revoke all on function public.erase_member_persona(uuid, bigint) from public;
grant execute on function public.erase_member_persona(uuid, bigint) to authenticated;
