-- pithub: 주제에 다른 이름 붙이기 (그래프 C)
--
-- 글자 유사도(trigram)는 "평가 분할"과 "train/test split"처럼 언어가 다른 같은 뜻을 잡지 못한다.
-- 사람이 주제에 별칭을 붙이면, 이후 그 이름으로 들어오는 기록이 이 주제로 모인다(서버·SQL 모두 별칭을 찾는다).
-- 다룰 수 있는 사람은 합치기와 같다: 개인 노드는 주인, 팀 노드는 팀원.

create function public.add_node_alias(node uuid, alias text) returns void
language plpgsql security definer set search_path = ''
as $$
declare
    norm text := public.normalize_node_name(alias);
    n public.nodes%rowtype;
begin
    if not public.can_curate_node(node) then
        raise exception 'cannot curate this node' using errcode = 'insufficient_privilege';
    end if;
    if norm = '' then
        raise exception 'empty alias' using errcode = 'invalid_parameter_value';
    end if;
    select * into n from public.nodes where id = node;
    -- 같은 이름 공간에 그 이름의 다른 노드가 이미 있으면 별칭이 아니라 합치기를 해야 한다
    if exists (
        select 1 from public.nodes o
         where o.id <> node and o.merged_into is null and o.kind = n.kind
           and o.team_id is not distinct from n.team_id and o.owner_github_id is not distinct from n.owner_github_id
           and (o.norm_name = norm or norm = any (o.aliases))
    ) then
        raise exception 'another topic already has this name — merge them instead' using errcode = 'unique_violation';
    end if;
    update public.nodes set aliases = array(select distinct unnest(aliases || norm)) where id = node and norm <> norm_name;
end
$$;

revoke all on function public.add_node_alias(uuid, text) from public;
grant execute on function public.add_node_alias(uuid, text) to authenticated;
