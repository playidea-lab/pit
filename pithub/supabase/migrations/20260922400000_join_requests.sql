-- pithub: 가입 요청 — 팀 주소로 처음 온 사람은 거부되지 않고 승인 대기열에 들어간다 (D-0008 보완)
--
-- 저장소 접근이 이미 신뢰다. 팀 커넥터로 인증한 비구성원은 team_members 에 "본인이 보낸" 행
-- (invited_by = github_id, accepted_at null)으로 들어가고, 소유자는 아이디를 입력하는 대신 승인만 누른다.
-- 승인 전에 그 사람이 팀 주소로 기록한 결정은 private 로 두었다가(source.team_status = pending),
-- 승인·수락 순간 팀 범위로 옮긴다 — 첫 기록이 버려지지 않는다.
--
-- 행의 두 뜻: invited_by = github_id → 가입 요청(소유자가 승인), invited_by <> github_id → 초대(본인이 수락).

-- 본인 수락은 초대에만. 가입 요청을 본인이 승인하면 안 된다.
drop policy team_members_accept_self on public.team_members;
create policy team_members_accept_invite_self on public.team_members
    for update to authenticated
    using (github_id = (select public.current_github_id()) and accepted_at is null
        and invited_by is distinct from github_id)
    with check (github_id = (select public.current_github_id()));

-- 소유자 승인은 가입 요청에만. 초대를 본인 대신 수락하면 안 된다.
create policy team_members_approve_request_owner on public.team_members
    for update to authenticated
    using (public.is_team_owner(team_id) and accepted_at is null and invited_by = github_id)
    with check (public.is_team_owner(team_id));

-- 승인·수락되는 순간, 대기 중이던 팀 주소 기록을 팀 범위로 옮긴다.
create function public.promote_pending_team_decisions() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
    team_slug text;
begin
    if new.accepted_at is null or old.accepted_at is not null then
        return new;
    end if;
    select slug into team_slug from public.teams where id = new.team_id;
    update public.decisions
       set visibility = 'team', team_id = new.team_id, source = source - 'team_status'
     where owner_github_id = new.github_id
       and visibility = 'private'
       and source ->> 'team' = team_slug
       and source ->> 'team_status' = 'pending';
    return new;
end
$$;

create trigger team_members_promote_pending
    after update of accepted_at on public.team_members
    for each row execute function public.promote_pending_team_decisions();
