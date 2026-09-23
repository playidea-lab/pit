-- pithub: 건너간 판단 (G0, docs/GRAPH_ENGINEERING.md)
--
-- 한 사람의 판단을 다른 사람의 AI가 get_decision 으로 가져간 순간 = 판단이 사람 사이를 건너간 사건.
-- 제품의 북극성 지표(D-0009 §1)이자 그래프의 cites 엣지다. 쓰는 것은 MCP 서버(service_role)뿐이다.

create table public.transfers (
    id bigint generated always as identity primary key,
    decision_id text not null references public.decisions (id) on delete cascade,
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,
    reader_github_id bigint not null references public.accounts (github_id) on delete cascade,
    team_id uuid references public.teams (id) on delete cascade,
    via text not null check (via in ('get', 'twin')),
    client text,
    created_at timestamptz not null default now(),
    check (owner_github_id <> reader_github_id)
);

create index transfers_team_idx on public.transfers (team_id, created_at desc);
create index transfers_owner_idx on public.transfers (owner_github_id, created_at desc);

alter table public.transfers enable row level security;
revoke all on public.transfers from anon, authenticated;
grant select on public.transfers to authenticated;

-- 판단의 주인과 가져간 사람만 개별 행을 본다
create policy transfers_select_involved on public.transfers
    for select to authenticated
    using ((select public.current_github_id()) in (owner_github_id, reader_github_id));

-- 팀원은 개별 행 대신 팀의 건수만 본다
create function public.team_transfer_count(team uuid, since timestamptz) returns bigint
language sql stable security definer set search_path = ''
as $$
    select case when public.is_team_member(team)
        then (select count(*) from public.transfers where team_id = team and created_at >= since)
        else 0 end
$$;

revoke all on function public.team_transfer_count(uuid, timestamptz) from public;
grant execute on function public.team_transfer_count(uuid, timestamptz) to authenticated;
