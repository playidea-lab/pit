-- pithub: 이름 맞추기 (G3, docs/GRAPH_ENGINEERING.md)
--
-- AI는 같은 주제를 "평가 분할", "train/test split", "평가 데이터 분할"로 제각각 부른다.
-- 이름이 비슷한 노드 쌍을 후보로 보여 주고, 사람이 합치거나 "다른 주제"라고 답한다.
-- 합치면 없어지는 노드의 이름이 남는 노드의 별칭이 되어, 이후 같은 이름의 기록도 남는 노드로 간다.

-- 이 유사도 이상이면 후보로 묻는다 (pg_trgm). 서버·웹에서 바꾸지 않고 여기 한 곳에서 조정한다.
create function public.node_merge_threshold() returns real
language sql immutable
as $$ select 0.4::real $$;

alter table public.nodes add column merged_by bigint references public.accounts (github_id) on delete set null;

create table public.node_merge_dismissals (
    node_a uuid not null references public.nodes (id) on delete cascade,
    node_b uuid not null references public.nodes (id) on delete cascade,
    dismissed_by bigint references public.accounts (github_id) on delete set null,
    created_at timestamptz not null default now(),
    primary key (node_a, node_b),
    check (node_a < node_b)
);

alter table public.node_merge_dismissals enable row level security;
revoke all on public.node_merge_dismissals from anon, authenticated;

-- 이 노드를 합치거나 판단할 수 있는가: 개인 노드는 주인, 팀 노드는 팀원
create function public.can_curate_node(node uuid) returns boolean
language sql stable security definer set search_path = ''
as $$
    select exists (
        select 1 from public.nodes n
        where n.id = node and n.merged_into is null
          and (n.owner_github_id = public.current_github_id() or public.is_team_member(n.team_id))
    )
$$;

-- 내가 다룰 수 있는 이름 공간에서, 이름이 비슷한 살아 있는 노드 쌍 (많이 쓰인 쪽을 keep 으로)
create function public.node_merge_candidates(max_pairs integer default 20)
returns table (keep_id uuid, keep_name text, keep_count bigint, drop_id uuid, drop_name text, drop_count bigint,
               kind text, similarity real)
-- pg_trgm 이 운영(Supabase: extensions)과 시험 DB(public)에서 다른 스키마에 있다 — 둘 다 찾게 한다. 테이블은 모두 스키마를 붙여 쓴다.
language sql stable security definer set search_path = public, extensions, pg_temp
as $$
    with mine as (
        select n.*, (select count(*) from public.decision_nodes dn where dn.node_id = n.id) as uses
        from public.nodes n
        where n.merged_into is null
          and (n.owner_github_id = public.current_github_id() or public.is_team_member(n.team_id))
    ),
    pairs as (
        select a.id as a_id, a.name as a_name, a.uses as a_uses, b.id as b_id, b.name as b_name, b.uses as b_uses,
               a.kind, similarity(a.norm_name, b.norm_name) as sim
        from mine a
        join mine b on a.id < b.id and a.kind = b.kind
                   and a.team_id is not distinct from b.team_id and a.owner_github_id is not distinct from b.owner_github_id
        where similarity(a.norm_name, b.norm_name) >= public.node_merge_threshold()
          and not exists (select 1 from public.node_merge_dismissals d where d.node_a = a.id and d.node_b = b.id)
    )
    select case when a_uses >= b_uses then a_id else b_id end, case when a_uses >= b_uses then a_name else b_name end,
           greatest(a_uses, b_uses),
           case when a_uses >= b_uses then b_id else a_id end, case when a_uses >= b_uses then b_name else a_name end,
           least(a_uses, b_uses), kind, sim
    from pairs order by sim desc limit max_pairs
$$;

create function public.merge_nodes(keep uuid, drop_node uuid) returns void
language plpgsql security definer set search_path = ''
as $$
declare
    k public.nodes%rowtype;
    d public.nodes%rowtype;
begin
    if keep = drop_node or not public.can_curate_node(keep) or not public.can_curate_node(drop_node) then
        raise exception 'cannot merge these nodes' using errcode = 'insufficient_privilege';
    end if;
    select * into k from public.nodes where id = keep;
    select * into d from public.nodes where id = drop_node;
    if k.kind <> d.kind or k.team_id is distinct from d.team_id or k.owner_github_id is distinct from d.owner_github_id then
        raise exception 'nodes are in different namespaces or kinds' using errcode = 'invalid_parameter_value';
    end if;

    insert into public.decision_nodes (decision_id, node_id, relation)
    select decision_id, keep, relation from public.decision_nodes where node_id = drop_node
    on conflict do nothing;
    delete from public.decision_nodes where node_id = drop_node;
    update public.nodes
       set aliases = (select array_agg(distinct x) from unnest(k.aliases || d.aliases || d.norm_name) as x where x <> k.norm_name)
     where id = keep;
    update public.nodes set merged_into = keep, merged_by = public.current_github_id(), aliases = '{}' where id = drop_node;
end
$$;

create function public.dismiss_node_merge(node_x uuid, node_y uuid) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if not public.can_curate_node(node_x) or not public.can_curate_node(node_y) then
        raise exception 'cannot judge these nodes' using errcode = 'insufficient_privilege';
    end if;
    insert into public.node_merge_dismissals (node_a, node_b, dismissed_by)
    values (least(node_x, node_y), greatest(node_x, node_y), public.current_github_id())
    on conflict do nothing;
end
$$;

revoke all on function public.node_merge_candidates(integer), public.merge_nodes(uuid, uuid), public.dismiss_node_merge(uuid, uuid) from public;
grant execute on function public.node_merge_candidates(integer), public.merge_nodes(uuid, uuid), public.dismiss_node_merge(uuid, uuid) to authenticated;
