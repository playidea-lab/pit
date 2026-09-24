-- pithub: 원칙 압축 제안 (그래프 G)
--
-- 같은 주제에서 같은 판정을 여러 번 내렸다면, 그 사람은 규칙을 갖고 있는 것이다.
-- 흩어진 판단 N건을 사람이 한 줄 원칙으로 압축하면: 원칙 결정(tags principle) 하나가 생기고,
-- 그 주제에 매달리며, 근거가 된 판단들을 cites 로 가리킨다. 검색·트윈은 원칙을 먼저 본다(principle: true).
-- 제안만 한다 — 원칙의 문장은 사람이 쓴다. 프로젝트 노드는 너무 넓어 후보에서 뺀다(주제·산출물만).

create function public.principle_min_support() returns integer
language sql immutable
as $$ select 3 $$;

-- 한 번 "원칙 아님"으로 넘긴 (주제, 판정)은 다시 제안하지 않는다
create table public.principle_dismissals (
    github_id bigint not null references public.accounts (github_id) on delete cascade,
    node_id uuid not null references public.nodes (id) on delete cascade,
    verdict text not null,
    created_at timestamptz not null default now(),
    primary key (github_id, node_id, verdict)
);

alter table public.principle_dismissals enable row level security;
revoke all on public.principle_dismissals from anon, authenticated;

-- 원칙으로 묶을 수 있는 내 판단 (반복 기록은 그 횟수만큼 센다 — 같은 거부를 세 번 한 것은 강한 신호다)
create function public.principle_members(node uuid, member_verdict text) returns text[]
language sql stable security definer set search_path = ''
as $$
    select coalesce(array_agg(d.id order by d.decided_at desc), '{}')
      from public.decisions d
      join public.decision_nodes dn on dn.decision_id = d.id and dn.node_id = node
     where d.owner_github_id = public.current_github_id()
       and d.status <> 'discarded' and d.verdict = member_verdict
       and not ('principle' = any (d.tags))
$$;

create function public.principle_candidates(max_rows integer default 10)
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
       and d.status <> 'discarded' and d.verdict is not null
       and not ('principle' = any (d.tags))
       -- 이미 그 주제에 내 원칙이 있으면 제안하지 않는다
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

create function public.compress_into_principle(node uuid, principle_verdict text, statement text) returns text
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    n public.nodes%rowtype;
    members text[] := public.principle_members(node, principle_verdict);
    principle_id text;
begin
    if me is null then
        raise exception 'not signed in' using errcode = '28000';
    end if;
    if length(btrim(coalesce(statement, ''))) not between 1 and 4000 then
        raise exception 'principle needs one line' using errcode = 'invalid_parameter_value';
    end if;
    select * into n from public.nodes where id = node and merged_into is null;
    if not found or cardinality(members) = 0 then
        raise exception 'no judgments of yours to compress here' using errcode = 'insufficient_privilege';
    end if;

    principle_id := 'PD-' || to_char(now(), 'YYYYMMDD') || '-pr' || substr(md5(node::text || principle_verdict || clock_timestamp()::text), 1, 8);
    insert into public.decisions (id, owner_github_id, status, visibility, team_id, origin, kind, verdict,
                                  situation, proposal, human_quote, tags, decided_at, source, dedupe_key)
    values (principle_id, me, 'confirmed', case when n.team_id is null then 'private' else 'team' end, n.team_id,
            'mcp', 'verdict', principle_verdict, '주제 "' || n.name || '"에서 반복된 판단을 원칙으로 정리',
            btrim(statement), btrim(statement), array['principle'], now(),
            jsonb_build_object('client', 'principle', 'support', cardinality(members)::text),
            'principle-' || node || '-' || principle_verdict || '-' || principle_id);
    insert into public.decision_nodes (decision_id, node_id) values (principle_id, node);
    insert into public.decision_links (from_decision, to_decision, relation, created_by)
    select principle_id, m, 'cites', me from unnest(members) as m
    on conflict do nothing;
    return principle_id;
end
$$;

create function public.dismiss_principle(node uuid, dismissed_verdict text) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if cardinality(public.principle_members(node, dismissed_verdict)) = 0 then
        raise exception 'no judgments of yours here' using errcode = 'insufficient_privilege';
    end if;
    insert into public.principle_dismissals (github_id, node_id, verdict)
    values (public.current_github_id(), node, dismissed_verdict)
    on conflict do nothing;
end
$$;

revoke all on function public.principle_members(uuid, text), public.principle_candidates(integer),
    public.compress_into_principle(uuid, text, text), public.dismiss_principle(uuid, text) from public;
grant execute on function public.principle_candidates(integer), public.compress_into_principle(uuid, text, text),
    public.dismiss_principle(uuid, text) to authenticated;
