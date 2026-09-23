-- pithub: 판단 그래프 스키마 (G1, docs/GRAPH_ENGINEERING.md)
--
-- 모든 엣지의 한쪽 끝은 결정이다 — 판단에 매달린 그래프(D-0009 §5)를 스키마로 강제한다.
-- 노드·엣지의 가시성은 부모 결정을 따른다: 본인 것이거나, 팀에 보인(확인됐거나 3일이 지난) 팀 결정.
-- 쓰기는 MCP 서버(service_role)와 DB 트리거만 한다.

-- 결정을 볼 수 있는가 — 노드·엣지 정책이 공유하는 한 곳
create function public.can_see_decision(decision_id text) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.decisions d
        where d.id = decision_id
          and (d.owner_github_id = public.current_github_id()
               or (public.is_team_shared(d.visibility, d.status, d.created_at) and public.is_team_member(d.team_id)))
    )
$$;

-- ---------------------------------------------------------------------------
-- 노드: 주제 · 프로젝트 · 산출물 (결정 노드는 decisions 자체)
-- ---------------------------------------------------------------------------

create table public.nodes (
    id uuid primary key default gen_random_uuid(),
    -- 이름 공간: 팀 노드는 팀이 공유하고, 팀 없는 결정의 노드는 그 사람 것이다
    team_id uuid references public.teams (id) on delete cascade,
    owner_github_id bigint references public.accounts (github_id) on delete cascade,
    kind text not null check (kind in ('topic', 'project', 'artifact')),
    name text not null check (length(name) between 1 and 120),
    -- 비교용 이름: 소문자 · 공백 하나 · 앞뒤 공백 없음 (서버 normalize_node_name 과 같아야 한다)
    norm_name text not null,
    aliases text[] not null default '{}',
    merged_into uuid references public.nodes (id) on delete set null,
    created_by bigint references public.accounts (github_id) on delete set null,
    created_at timestamptz not null default now(),
    check ((team_id is null) <> (owner_github_id is null))
);

create unique index nodes_unique_live on public.nodes
    (kind, norm_name, coalesce(team_id::text, ''), coalesce(owner_github_id, 0))
    where merged_into is null;
create index nodes_norm_trgm on public.nodes using gin (norm_name gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- 엣지
-- ---------------------------------------------------------------------------

-- 결정 → 노드 (about)
create table public.decision_nodes (
    decision_id text not null references public.decisions (id) on delete cascade,
    node_id uuid not null references public.nodes (id) on delete cascade,
    relation text not null default 'about' check (relation in ('about')),
    created_at timestamptz not null default now(),
    primary key (decision_id, node_id, relation)
);

create index decision_nodes_node_idx on public.decision_nodes (node_id);

-- 결정 → 결정
create table public.decision_links (
    id bigint generated always as identity primary key,
    from_decision text not null references public.decisions (id) on delete cascade,
    to_decision text not null references public.decisions (id) on delete cascade,
    relation text not null check (relation in ('supersedes', 'conflicts_with', 'depends_on')),
    -- 충돌은 서버가 후보로 올리고(proposed) 사람이 확인한다
    status text not null default 'confirmed' check (status in ('proposed', 'confirmed')),
    created_by bigint references public.accounts (github_id) on delete set null,
    created_at timestamptz not null default now(),
    unique (from_decision, to_decision, relation),
    check (from_decision <> to_decision)
);

create index decision_links_to_idx on public.decision_links (to_decision);

-- ---------------------------------------------------------------------------
-- 접근 권한 — 읽기만, 부모 결정을 따른다
-- ---------------------------------------------------------------------------

alter table public.nodes enable row level security;
alter table public.decision_nodes enable row level security;
alter table public.decision_links enable row level security;
revoke all on public.nodes, public.decision_nodes, public.decision_links from anon, authenticated;
grant select on public.nodes, public.decision_nodes, public.decision_links to authenticated;

create policy decision_nodes_select_visible on public.decision_nodes
    for select to authenticated using (public.can_see_decision(decision_id));

-- 노드 이름도 정보다: 볼 수 있는 결정이 하나라도 매달린 노드만 보인다
create policy nodes_select_visible on public.nodes
    for select to authenticated
    using (exists (
        select 1 from public.decision_nodes dn
        where dn.node_id = nodes.id and public.can_see_decision(dn.decision_id)
    ));

create policy decision_links_select_visible on public.decision_links
    for select to authenticated
    using (public.can_see_decision(from_decision) and public.can_see_decision(to_decision));

-- ---------------------------------------------------------------------------
-- supersedes 배열 → decision_links (배열은 호환을 위해 당분간 남기고 트리거로 맞춘다)
-- ---------------------------------------------------------------------------

create function public.sync_supersedes_links() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    delete from public.decision_links
     where from_decision = new.id and relation = 'supersedes'
       and not (to_decision = any (new.supersedes));
    insert into public.decision_links (from_decision, to_decision, relation, created_by)
    select new.id, target.id, 'supersedes', new.owner_github_id
      from public.decisions target
     where target.id = any (new.supersedes) and target.id <> new.id
    on conflict (from_decision, to_decision, relation) do nothing;
    return new;
end
$$;

create trigger decisions_sync_supersedes
    after insert or update of supersedes on public.decisions
    for each row execute function public.sync_supersedes_links();

insert into public.decision_links (from_decision, to_decision, relation, created_by)
select d.id, target.id, 'supersedes', d.owner_github_id
  from public.decisions d
  join public.decisions target on target.id = any (d.supersedes) and target.id <> d.id
on conflict (from_decision, to_decision, relation) do nothing;
