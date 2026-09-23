-- pithub: 기존 결정을 그래프에 매단다 (그래프 A — 비용 0)
--
-- 그래프 이전에 쌓인 결정에는 노드가 없다. 모든 결정이 가진 source.project 를 프로젝트 노드로 올린다.
-- 이름 비교 규칙은 서버의 normalize_node_name(pit/server/graph.py)과 같아야 한다 — 시험이 둘을 대조한다.

create function public.normalize_node_name(name text) returns text
language sql immutable
as $$
    select btrim(regexp_replace(
        regexp_replace(lower(normalize(coalesce(name, ''), NFKC)), '[,(){}"\\*%]', ' ', 'g'),
        '\s+', ' ', 'g'))
$$;

-- 결정 하나에 이름 하나를 매단다. 노드가 없으면 만든다. 이름 공간은 결정을 따른다(팀 결정이면 팀, 아니면 주인).
create function public.attach_node_by_name(decision text, node_kind text, node_name text) returns uuid
language plpgsql security definer set search_path = ''
as $$
declare
    d public.decisions%rowtype;
    norm text := public.normalize_node_name(node_name);
    team uuid;
    owner bigint;
    node uuid;
begin
    select * into d from public.decisions where id = decision;
    if not found or norm = '' then
        return null;
    end if;
    if d.visibility = 'team' and d.team_id is not null then
        team := d.team_id;
    else
        owner := d.owner_github_id;
    end if;
    select n.id into node from public.nodes n
     where n.kind = node_kind and n.merged_into is null
       and n.team_id is not distinct from team and n.owner_github_id is not distinct from owner
       and (n.norm_name = norm or norm = any (n.aliases))
     limit 1;
    if node is null then
        insert into public.nodes (team_id, owner_github_id, kind, name, norm_name, created_by)
        values (team, owner, node_kind, btrim(node_name), norm, d.owner_github_id)
        returning id into node;
    end if;
    insert into public.decision_nodes (decision_id, node_id) values (decision, node) on conflict do nothing;
    return node;
end;
$$;

revoke all on function public.attach_node_by_name(text, text, text) from public, anon, authenticated;

-- 한 번: 모든 결정의 프로젝트를 노드로
select public.attach_node_by_name(d.id, 'project', d.source ->> 'project')
  from public.decisions d
 where d.status <> 'discarded' and coalesce(d.source ->> 'project', '') <> '';
