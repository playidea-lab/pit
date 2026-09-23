-- pithub: 초대 링크 (2026-09-24 사용자 결정 — 링크로 들어오면 승인 없이 바로 팀원)
--
-- 팀마다 살아 있는 링크는 하나다. 다시 만들면 이전 링크는 무효가 되고, 기본 7일 뒤 만료된다.
-- 토큰 원문은 저장하지 않고 해시만 둔다 — 원문은 만든 순간 관리자에게 한 번만 보인다.

alter table public.teams
    add column invite_token_hash text,
    add column invite_expires_at timestamptz;

create function public.invite_valid_for() returns interval
language sql immutable
as $$ select interval '7 days' $$;

-- 팀 소유자만: 새 링크 토큰을 만들어 원문을 돌려준다 (이전 링크는 무효)
create function public.create_team_invite(team uuid) returns text
language plpgsql security definer set search_path = ''
as $$
declare
    token text := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
begin
    if not public.is_team_owner(team) then
        raise exception 'not a team owner' using errcode = 'insufficient_privilege';
    end if;
    update public.teams
       set invite_token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex'),
           invite_expires_at = now() + public.invite_valid_for()
     where id = team;
    return token;
end
$$;

create function public.revoke_team_invite(team uuid) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if not public.is_team_owner(team) then
        raise exception 'not a team owner' using errcode = 'insufficient_privilege';
    end if;
    update public.teams set invite_token_hash = null, invite_expires_at = null where id = team;
end
$$;

-- 링크로 합류: 로그인한 사람을 곧바로 구성원으로. 가입 요청 중이었으면 그 요청이 수락되고(트리거가 대기 기록을 팀으로 옮긴다),
-- 이미 구성원이면 아무 일도 없다. 합류한 팀의 slug 를 돌려준다.
create function public.join_team_with_invite(token text) returns text
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    t public.teams%rowtype;
begin
    if me is null then
        raise exception 'not signed in' using errcode = 'insufficient_privilege';
    end if;
    select * into t from public.teams
     where invite_token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex') and invite_expires_at > now();
    if not found then
        raise exception 'invite link is invalid or expired' using errcode = 'no_data_found';
    end if;
    insert into public.team_members (team_id, github_id, role, invited_by, accepted_at)
    values (t.id, me, 'member', t.created_by, now())
    on conflict (team_id, github_id) do update set accepted_at = coalesce(public.team_members.accepted_at, now());
    return t.slug;
end
$$;

revoke all on function public.create_team_invite(uuid), public.revoke_team_invite(uuid), public.join_team_with_invite(text) from public;
grant execute on function public.create_team_invite(uuid), public.revoke_team_invite(uuid), public.join_team_with_invite(text) to authenticated;
