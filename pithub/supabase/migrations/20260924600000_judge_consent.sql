-- pithub: 외부 판정기 동의 (D-0009 §7)
--
-- 팀 범위 결정을 외부 판정기(JEV, TypeSafe AI)로 보내려면 팀 소유자의 명시적 동의가 있어야 한다.
-- 누가 언제 동의했는지 남긴다. 동의하지 않은 팀의 결정으로는 무료 판정기(서버 안의 kNN)만 쓴다.

alter table public.teams
    add column external_judge_consent_at timestamptz,
    add column external_judge_consent_by bigint references public.accounts (github_id) on delete set null;

create function public.set_team_judge_consent(team uuid, consent boolean) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if not public.is_team_owner(team) then
        raise exception 'not a team owner' using errcode = 'insufficient_privilege';
    end if;
    update public.teams
       set external_judge_consent_at = case when consent then now() else null end,
           external_judge_consent_by = case when consent then public.current_github_id() else null end
     where id = team;
end
$$;

revoke all on function public.set_team_judge_consent(uuid, boolean) from public;
grant execute on function public.set_team_judge_consent(uuid, boolean) to authenticated;
