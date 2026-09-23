-- pithub: 트윈에게 묻기 (G6, docs/GRAPH_ENGINEERING.md) — 서버 설정 PITHUB_TWIN_ENABLED 로 열기 전까지 쓰이지 않는다
--
-- 트윈이 확신하지 못하면 답하지 않고 본인에게 묻는다. 본인의 답은 그 사람의 새 결정이 되어
-- 다음 판정의 근거가 된다(라벨). 질문한 사람과 트윈의 주인만 질문을 본다.

create table public.twin_questions (
    id bigint generated always as identity primary key,
    asker_github_id bigint not null references public.accounts (github_id) on delete cascade,
    twin_github_id bigint not null references public.accounts (github_id) on delete cascade,
    team_id uuid references public.teams (id) on delete cascade,
    situation text not null default '',
    proposal text not null check (length(proposal) between 1 and 4000),
    confidence real,
    answer_decision_id text references public.decisions (id) on delete set null,
    answered_at timestamptz,
    created_at timestamptz not null default now(),
    check (asker_github_id <> twin_github_id)
);

create index twin_questions_twin_idx on public.twin_questions (twin_github_id, answered_at, created_at desc);

alter table public.twin_questions enable row level security;
revoke all on public.twin_questions from anon, authenticated;
grant select on public.twin_questions to authenticated;
create policy twin_questions_select_involved on public.twin_questions
    for select to authenticated
    using ((select public.current_github_id()) in (asker_github_id, twin_github_id));

-- 트윈의 주인이 답한다: 답은 주인의 확인된 결정이 된다. 질문이 팀에서 왔으면 팀 범위로.
create function public.answer_twin_question(question_id bigint, answer_verdict text, answer_quote text)
returns text
language plpgsql security definer set search_path = ''
as $$
declare
    q public.twin_questions%rowtype;
    decision_id text;
begin
    select * into q from public.twin_questions where id = question_id;
    if not found or q.twin_github_id <> public.current_github_id() then
        raise exception 'not your question' using errcode = 'insufficient_privilege';
    end if;
    if q.answered_at is not null then
        raise exception 'already answered' using errcode = 'invalid_parameter_value';
    end if;
    if answer_verdict not in ('approve', 'modify', 'reject') or length(coalesce(answer_quote, '')) not between 1 and 4000 then
        raise exception 'invalid answer' using errcode = 'invalid_parameter_value';
    end if;

    decision_id := 'PD-' || to_char(now(), 'YYYYMMDD') || '-tq' || q.id;
    insert into public.decisions (id, owner_github_id, status, visibility, team_id, origin, kind, verdict,
                                  situation, proposal, human_quote, decided_at, source, dedupe_key)
    values (decision_id, q.twin_github_id, 'confirmed', case when q.team_id is null then 'private' else 'team' end,
            q.team_id, 'mcp', 'verdict', answer_verdict, q.situation, q.proposal, answer_quote, now(),
            jsonb_build_object('client', 'twin-answer', 'question_id', q.id::text), 'twin-question-' || q.id);
    update public.twin_questions set answer_decision_id = decision_id, answered_at = now() where id = question_id;
    return decision_id;
end
$$;

revoke all on function public.answer_twin_question(bigint, text, text) from public;
grant execute on function public.answer_twin_question(bigint, text, text) to authenticated;

-- consult_log 는 G6부터 쓴다: 트윈이 답했든 기권했든, 누가 무엇을 물었는지 주인이 본다 (D-0009 §3)
alter table public.consult_log
    add column confidence real,
    add column abstained boolean not null default false;
