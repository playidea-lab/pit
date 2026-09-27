-- pithub: 원칙 압축의 권한·무결성 보강 (2026-09-27 리뷰)
--
-- 1) 노드를 다룰 수 있는 사람만 (can_curate_node): 팀에서 나간 사람이 옛 팀 주제에 확정 원칙을 넣지 못하게.
--    원칙은 확정 상태로 만들어져 3일 유예 없이 팀에 보이고, 본인은 지울 수 없다 — 그래서 문은 좁아야 한다.
-- 2) 근거는 노드와 같은 이름 공간의 판단만: 팀 노드면 그 팀의 팀 판단, 개인 노드면 본인의 개인 판단.
--    (팀 초안을 개인으로 돌린 판단을 팀 원칙이 가리키지 않게)
-- 3) 후보와 같은 조건: 주제·산출물만, 최소 근거 수, 같은 주제·판정의 원칙은 하나.

create or replace function public.principle_members(node uuid, member_verdict text) returns text[]
language sql stable security definer set search_path = ''
as $$
    select coalesce(array_agg(d.id order by d.decided_at desc), '{}')
      from public.decisions d
      join public.decision_nodes dn on dn.decision_id = d.id and dn.node_id = node
      join public.nodes n on n.id = node
     where d.owner_github_id = public.current_github_id()
       and d.status <> 'discarded' and d.verdict = member_verdict
       and not ('principle' = any (d.tags))
       and (case when n.team_id is null then d.visibility = 'private'
                 else d.visibility = 'team' and d.team_id = n.team_id end)
$$;

create or replace function public.compress_into_principle(node uuid, principle_verdict text, statement text) returns text
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    n public.nodes%rowtype;
    members text[];
    support bigint;
    principle_id text;
begin
    if me is null then
        raise exception 'not signed in' using errcode = '28000';
    end if;
    if not public.can_curate_node(node) then
        raise exception 'cannot curate this node' using errcode = 'insufficient_privilege';
    end if;
    if length(btrim(coalesce(statement, ''))) not between 1 and 4000 then
        raise exception 'principle needs one line' using errcode = 'invalid_parameter_value';
    end if;
    select * into n from public.nodes where id = node;
    if n.kind not in ('topic', 'artifact') then
        raise exception 'principles live on topics or artifacts' using errcode = 'invalid_parameter_value';
    end if;
    members := public.principle_members(node, principle_verdict);
    select coalesce(sum(repeat_count), 0) into support from public.decisions where id = any (members);
    if support < public.principle_min_support() then
        raise exception 'not enough judgments to compress' using errcode = 'insufficient_privilege';
    end if;
    if exists (
        select 1 from public.decisions p join public.decision_nodes pn on pn.decision_id = p.id
         where pn.node_id = node and p.owner_github_id = me and p.status <> 'discarded'
           and p.verdict = principle_verdict and 'principle' = any (p.tags)
    ) then
        raise exception 'a principle already exists here' using errcode = 'unique_violation';
    end if;

    principle_id := 'PD-' || to_char(now(), 'YYYYMMDD') || '-pr' || substr(md5(node::text || principle_verdict || clock_timestamp()::text), 1, 8);
    insert into public.decisions (id, owner_github_id, status, visibility, team_id, origin, kind, verdict,
                                  situation, proposal, human_quote, tags, decided_at, source, dedupe_key)
    values (principle_id, me, 'confirmed', case when n.team_id is null then 'private' else 'team' end, n.team_id,
            'mcp', 'verdict', principle_verdict, '주제 "' || n.name || '"에서 반복된 판단을 원칙으로 정리',
            btrim(statement), btrim(statement), array['principle'], now(),
            jsonb_build_object('client', 'principle', 'support', support::text),
            'principle-' || node || '-' || principle_verdict || '-' || principle_id);
    insert into public.decision_nodes (decision_id, node_id) values (principle_id, node);
    insert into public.decision_links (from_decision, to_decision, relation, created_by)
    select principle_id, m, 'cites', me from unnest(members) as m
    on conflict do nothing;
    return principle_id;
end
$$;

create or replace function public.dismiss_principle(node uuid, dismissed_verdict text) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if not public.can_curate_node(node) or cardinality(public.principle_members(node, dismissed_verdict)) = 0 then
        raise exception 'no judgments of yours here' using errcode = 'insufficient_privilege';
    end if;
    insert into public.principle_dismissals (github_id, node_id, verdict)
    values (public.current_github_id(), node, dismissed_verdict)
    on conflict do nothing;
end
$$;

-- 후보도 같은 문: 다룰 수 없는 노드(떠난 팀의 주제)는 제안하지 않는다
create or replace function public.principle_candidates(max_rows integer default 10)
returns table (node_id uuid, node_name text, verdict text, support bigint, decision_ids text[], proposals text[])
language sql stable security definer set search_path = ''
as $$
    select n.id, n.name, d.verdict, sum(d.repeat_count)::bigint,
           array_agg(d.id order by d.decided_at desc),
           (array_agg(d.proposal order by d.decided_at desc))[1:3]
      from public.decisions d
      join public.decision_nodes dn on dn.decision_id = d.id
      join public.nodes n on n.id = dn.node_id and n.merged_into is null and n.kind in ('topic', 'artifact')
     where d.owner_github_id = public.current_github_id()
       and public.can_curate_node(n.id)
       and d.status <> 'discarded' and d.verdict is not null
       and not ('principle' = any (d.tags))
       and (case when n.team_id is null then d.visibility = 'private'
                 else d.visibility = 'team' and d.team_id = n.team_id end)
       and not exists (
           select 1 from public.decisions p join public.decision_nodes pn on pn.decision_id = p.id
            where pn.node_id = n.id and p.owner_github_id = d.owner_github_id
              and p.status <> 'discarded' and 'principle' = any (p.tags))
       and not exists (
           select 1 from public.principle_dismissals x
            where x.github_id = d.owner_github_id and x.node_id = n.id and x.verdict = d.verdict)
     group by n.id, n.name, d.verdict
    having sum(d.repeat_count) >= public.principle_min_support()
     order by sum(d.repeat_count) desc, n.name
     limit max_rows
$$;
