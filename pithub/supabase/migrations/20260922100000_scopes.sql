-- pithub: 공개 범위 4단계(private · team · friends · public), 팀, 친구, 자문 기록
--
-- 원칙: 트윈은 하나가 아니다. 묻는 사람이 볼 수 있는 결정만큼만 아는 트윈이다.
-- 그 경계를 프롬프트가 아니라 여기(행 접근 권한)에서 만든다.
--
-- visibility 는 "공유 의도"다. 초안(draft)에도 붙을 수 있지만, 남에게 실제로 보이는 것은
-- 언제나 status = 'confirmed' 인 행뿐이다 — 아래 모든 공유 정책과 공개 뷰가 그 조건을 건다.

-- ---------------------------------------------------------------------------
-- 팀 · 친구
-- ---------------------------------------------------------------------------

create table public.teams (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,38}$'),
    name text not null,
    created_by bigint not null references public.accounts (github_id) on delete restrict,
    created_at timestamptz not null default now()
);

create table public.team_members (
    team_id uuid not null references public.teams (id) on delete cascade,
    github_id bigint not null references public.accounts (github_id) on delete cascade,
    role text not null default 'member' check (role in ('owner', 'member')),
    joined_at timestamptz not null default now(),
    primary key (team_id, github_id)
);

-- 한 쌍에 한 행. accepted 가 true 면 서로 친구다 (상호).
create table public.follows (
    from_github_id bigint not null references public.accounts (github_id) on delete cascade,
    to_github_id bigint not null references public.accounts (github_id) on delete cascade,
    accepted boolean not null default false,
    created_at timestamptz not null default now(),
    primary key (from_github_id, to_github_id),
    check (from_github_id <> to_github_id)
);

-- 프로젝트별 기본 공개 범위. 없으면 private.
create table public.project_defaults (
    github_id bigint not null references public.accounts (github_id) on delete cascade,
    project text not null,
    visibility text not null check (visibility in ('private', 'team', 'friends', 'public')),
    team_id uuid references public.teams (id) on delete cascade,
    primary key (github_id, project),
    check ((visibility = 'team') = (team_id is not null))
);

-- 누가 누구의 트윈에 무엇을 물었나. 트윈 주인만 읽는다.
create table public.consult_log (
    id bigint generated always as identity primary key,
    asker_github_id bigint not null references public.accounts (github_id) on delete cascade,
    twin_github_id bigint not null references public.accounts (github_id) on delete cascade,
    question text not null,
    decision_ids text[] not null default '{}',
    created_at timestamptz not null default now()
);

create index consult_log_twin_idx on public.consult_log (twin_github_id, created_at desc);

create function public.is_team_member(team uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.team_members
        where team_id = team and github_id = public.current_github_id()
    )
$$;

create function public.are_friends(other bigint) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.follows f
        where f.accepted
          and ((f.from_github_id = public.current_github_id() and f.to_github_id = other)
            or (f.to_github_id = public.current_github_id() and f.from_github_id = other))
    )
$$;

-- ---------------------------------------------------------------------------
-- decisions: 범위 확장
-- ---------------------------------------------------------------------------

alter table public.decisions drop constraint decisions_visibility_check;
alter table public.decisions add constraint decisions_visibility_check
    check (visibility in ('private', 'team', 'friends', 'public'));

-- "확정되지 않으면 공개 불가"는 제약이 아니라 정책으로 옮긴다 (범위는 의도, 노출은 확정 뒤).
alter table public.decisions drop constraint decisions_unconfirmed_private_check;

alter table public.decisions
    add column team_id uuid references public.teams (id) on delete set null,
    -- 이 결정을 내릴 때 참고한 (사람, 결정) 목록: [{"github_id": 1, "decision_id": "PD-…", "predicted": "reject"}]
    -- 사람 사이의 결정 그래프이자, 트윈 예측을 본 뒤의 결정을 그 트윈의 평가에서 빼는 근거다.
    add column consulted jsonb not null default '[]'::jsonb,
    add constraint decisions_team_scope_check check ((visibility = 'team') = (team_id is not null));

grant update (team_id, consulted) on public.decisions to authenticated;

drop view public.public_decisions;
create view public.public_decisions
with (security_invoker = false)
as
select
    d.id, a.github_login, a.avatar_url, d.kind, d.verdict, d.reject_kind, d.situation, d.proposal,
    d.options, d.chosen, d.rationale, d.human_quote, d.tags, d.supersedes, d.consulted, d.decided_at
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
where d.status = 'confirmed' and d.visibility = 'public';

grant select on public.public_decisions to anon, authenticated;

-- 팀원의 team 범위 결정과 친구의 friends 범위 결정 — 확정된 것만
create policy decisions_select_team on public.decisions
    for select to authenticated
    using (status = 'confirmed' and visibility = 'team' and public.is_team_member(team_id));

create policy decisions_select_friends on public.decisions
    for select to authenticated
    using (status = 'confirmed' and visibility = 'friends' and public.are_friends(owner_github_id));

-- ---------------------------------------------------------------------------
-- 접근 권한
-- ---------------------------------------------------------------------------

alter table public.teams enable row level security;
alter table public.team_members enable row level security;
alter table public.follows enable row level security;
alter table public.project_defaults enable row level security;
alter table public.consult_log enable row level security;

revoke all on public.teams, public.team_members, public.follows, public.project_defaults, public.consult_log
    from anon, authenticated;
grant select, insert on public.teams to authenticated;
grant select, insert, delete on public.team_members to authenticated;
grant select, insert, update, delete on public.follows to authenticated;
grant select, insert, update, delete on public.project_defaults to authenticated;
grant select on public.consult_log to authenticated;

create policy teams_select_member on public.teams
    for select to authenticated using (public.is_team_member(id));
create policy teams_insert_self on public.teams
    for insert to authenticated with check (created_by = (select public.current_github_id()));

create policy team_members_select_member on public.team_members
    for select to authenticated using (public.is_team_member(team_id));
-- 팀 소유자만 초대하고 내보낸다. 본인은 스스로 나갈 수 있다.
create policy team_members_insert_owner on public.team_members
    for insert to authenticated
    with check (exists (
        select 1 from public.team_members m
        where m.team_id = team_members.team_id and m.github_id = (select public.current_github_id()) and m.role = 'owner'
    ) or (github_id = (select public.current_github_id()) and exists (
        select 1 from public.teams t where t.id = team_id and t.created_by = github_id
    )));
create policy team_members_delete_self_or_owner on public.team_members
    for delete to authenticated
    using (github_id = (select public.current_github_id()) or exists (
        select 1 from public.team_members m
        where m.team_id = team_members.team_id and m.github_id = (select public.current_github_id()) and m.role = 'owner'
    ));

create policy follows_select_involved on public.follows
    for select to authenticated
    using ((select public.current_github_id()) in (from_github_id, to_github_id));
create policy follows_insert_from_self on public.follows
    for insert to authenticated
    with check (from_github_id = (select public.current_github_id()) and accepted = false);
-- 수락은 받는 쪽만
create policy follows_accept_by_target on public.follows
    for update to authenticated
    using (to_github_id = (select public.current_github_id()))
    with check (to_github_id = (select public.current_github_id()));
create policy follows_delete_involved on public.follows
    for delete to authenticated
    using ((select public.current_github_id()) in (from_github_id, to_github_id));

create policy project_defaults_own on public.project_defaults
    for all to authenticated
    using (github_id = (select public.current_github_id()))
    with check (github_id = (select public.current_github_id())
        and (team_id is null or public.is_team_member(team_id)));

create policy consult_log_select_twin_owner on public.consult_log
    for select to authenticated using (twin_github_id = (select public.current_github_id()));
