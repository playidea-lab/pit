-- pithub: 트윈 판정기 그림자 비교 (2026-09-24 사용자 결정: kNN 우선 + JEV 그림자)
--
-- 오프라인 시험에서 이 설정의 JEV(0.389)가 무료 kNN(0.456)보다 낫지 않았다. 답은 kNN이 하고,
-- JEV는 같은 질문을 따로 판정해 기록만 한다. 트윈 주인이 "당신이라면?"에 답하면 두 판정기의 채점 기준이 된다.

alter table public.consult_log
    add column prediction text check (prediction in ('approve', 'modify', 'reject')),
    add column judge text,
    add column shadow_judge text,
    add column shadow_prediction text check (shadow_prediction in ('approve', 'modify', 'reject')),
    add column shadow_confidence real,
    add column owner_verdict text check (owner_verdict in ('approve', 'modify', 'reject')),
    add column rated_at timestamptz;

-- 트윈 주인만 채점한다
create function public.rate_twin_answer(consult_id bigint, verdict text) returns void
language plpgsql security definer set search_path = ''
as $$
begin
    if verdict not in ('approve', 'modify', 'reject') then
        raise exception 'invalid verdict' using errcode = 'invalid_parameter_value';
    end if;
    update public.consult_log set owner_verdict = verdict, rated_at = now()
     where id = consult_id and twin_github_id = public.current_github_id();
    if not found then
        raise exception 'not your twin' using errcode = 'insufficient_privilege';
    end if;
end
$$;

revoke all on function public.rate_twin_answer(bigint, text) from public;
grant execute on function public.rate_twin_answer(bigint, text) to authenticated;
