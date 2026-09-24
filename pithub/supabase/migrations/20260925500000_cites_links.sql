-- pithub: 엣지 정리 (그래프 F)
--
-- "누구의 판단을 참고해 이 결정을 내렸나"를 결정 → 결정 링크 cites 로 둔다.
--   transfers  = 판단이 읽힌 사건 (사람 → 결정, 북극성 지표 — 그대로)
--   cites      = 그 판단이 실제로 다른 결정의 근거가 된 것 (결정 → 결정, 그래프의 엣지)
-- 같은 뜻으로 만들어 두고 한 번도 쓰이지 않은 decisions.consulted(jsonb)는 걷어낸다.

alter table public.decision_links drop constraint decision_links_relation_check;
alter table public.decision_links add constraint decision_links_relation_check
    check (relation in ('supersedes', 'conflicts_with', 'depends_on', 'cites'));

-- 혹시 들어 있는 consulted 는 버리지 않고 cites 로 옮긴다 (가리키는 결정이 있을 때만)
insert into public.decision_links (from_decision, to_decision, relation, created_by)
select d.id, target.id, 'cites', d.owner_github_id
  from public.decisions d
 cross join lateral jsonb_array_elements(d.consulted) c
  join public.decisions target on target.id = c ->> 'decision_id' and target.id <> d.id
on conflict (from_decision, to_decision, relation) do nothing;

-- 열을 쓰는 뷰를 내리고, 열을 지운 뒤 같은 모양으로 다시 만든다 (company_product 의 정의에서 consulted 만 뺌)
drop view public.team_decisions;
alter table public.decisions drop column consulted;

create view public.team_decisions
with (security_invoker = false)
as
select
    d.id, d.owner_github_id, a.github_login, a.avatar_url, a.deleted_at is not null as departed,
    d.team_id, t.slug as team_slug, d.status = 'confirmed' as verified,
    d.kind, d.verdict, d.reject_kind, d.situation, d.proposal, d.options, d.chosen, d.rationale,
    d.human_quote, d.tags, d.supersedes, d.decided_at, d.cited_count
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
join public.teams t on t.id = d.team_id
where public.is_team_shared(d.visibility, d.status, d.created_at) and public.is_team_member(d.team_id);

grant select on public.team_decisions to authenticated;
