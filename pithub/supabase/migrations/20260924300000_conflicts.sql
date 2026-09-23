-- pithub: 충돌 후보 처리 (G5, docs/GRAPH_ENGINEERING.md)
--
-- 서버가 같은 주제에서 반대로 판정된 결정 쌍을 conflicts_with(proposed) 로 올린다.
-- 사람이 정리함에서 셋 중 하나를 고른다 — 충돌 맞음 / 충돌 아님 / 새 결정이 옛 결정을 뒤집은 것.
-- 링크 한쪽 결정의 주인만 처리할 수 있다. 웹에는 decision_links 쓰기 권한이 없고 이 함수가 유일한 길이다.

create function public.resolve_conflict(link_id bigint, action text) returns void
language plpgsql security definer set search_path = ''
as $$
declare
    me bigint := public.current_github_id();
    link public.decision_links%rowtype;
    newer text;
    older text;
begin
    select * into link from public.decision_links
     where id = link_id and relation = 'conflicts_with';
    if not found then
        raise exception 'no such conflict' using errcode = 'no_data_found';
    end if;
    if not exists (
        select 1 from public.decisions d
         where d.id in (link.from_decision, link.to_decision) and d.owner_github_id = me
    ) then
        raise exception 'not your decision' using errcode = 'insufficient_privilege';
    end if;

    if action = 'confirm' then
        update public.decision_links set status = 'confirmed' where id = link_id;
    elsif action = 'dismiss' then
        delete from public.decision_links where id = link_id;
    elsif action = 'supersede' then
        -- 나중에 내린 결정이 먼저 것을 뒤집었다. 뒤집는 쪽(나중 것)의 주인만 그렇게 말할 수 있다.
        select d.id into newer from public.decisions d
         where d.id in (link.from_decision, link.to_decision) order by d.decided_at desc limit 1;
        older := case when newer = link.from_decision then link.to_decision else link.from_decision end;
        if not exists (select 1 from public.decisions where id = newer and owner_github_id = me) then
            raise exception 'only the author of the newer decision can supersede' using errcode = 'insufficient_privilege';
        end if;
        update public.decisions set supersedes = array_append(supersedes, older)
         where id = newer and not (older = any (supersedes));
        delete from public.decision_links where id = link_id;
    else
        raise exception 'unknown action %', action using errcode = 'invalid_parameter_value';
    end if;
end
$$;

revoke all on function public.resolve_conflict(bigint, text) from public;
grant execute on function public.resolve_conflict(bigint, text) to authenticated;
