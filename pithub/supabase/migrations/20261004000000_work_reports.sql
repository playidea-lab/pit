-- 작업 보고 (report_start / report_commit) — 에이전트가 일감 시작과 커밋 때 남기는 요약.
-- 결정(decisions)이 "무엇을 하기로 했나"라면, 작업 보고는 "그 결정을 어떻게 실행했나"다.
-- 보고는 주장일 뿐이고, 검증(원자성·실투입·규모)은 git_watcher 가 독립 근거로 한다.
--
-- 공개 범위 (대표 결정 2026-10-04): 본인과 그 팀의 소유자만 읽는다. 동료끼리는 서로의 보고를 보지 않는다.
-- 평가 근거가 되는 기록이라 결정과 달리 팀 공유 유예·공개 전환이 없다.

create table public.work_reports (
    id text primary key,
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,
    team_id uuid references public.teams (id) on delete set null,

    kind text not null check (kind in ('start', 'commit')),
    -- commit 보고가 어느 start 보고의 일감인지 (사전 추정과 대조하는 고리)
    start_id text references public.work_reports (id) on delete set null,

    task text not null,
    task_kind text not null check (task_kind in ('feature', 'fix', 'research', 'ops', 'docs', 'refactor')),
    repo text,
    commit_sha text,

    intent text not null default '',     -- 무엇을 지시받아 무엇을 했나 (요약, 원문 아님)
    position text not null default '',   -- 전체 업무에서 이 작업의 자리
    implements text[] not null default '{}',  -- 실행한 결정·목표 id

    -- start: 시작 전 예상 / commit: 다 하고 본 자기 추정
    expected_manual_hours numeric check (expected_manual_hours >= 0),
    expected_agent_minutes numeric check (expected_agent_minutes >= 0),

    atomic boolean,
    atomic_note text not null default '',
    message_ok boolean,
    message_note text not null default '',
    principles_kept text[] not null default '{}',
    principles_missed text[] not null default '{}',

    client text,
    redactions jsonb not null default '{}',
    reported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),

    constraint commit_has_sha check (kind <> 'commit' or commit_sha is not null)
);

create index work_reports_owner_time on public.work_reports (owner_github_id, reported_at desc);
create index work_reports_team_time on public.work_reports (team_id, reported_at desc);
create index work_reports_commit on public.work_reports (repo, commit_sha);

alter table public.work_reports enable row level security;

-- 쓰기는 서버(서비스 키)만 한다 — 웹·클라이언트에서 직접 쓰는 정책은 두지 않는다
create policy work_reports_select_self_or_team_owner on public.work_reports
    for select to authenticated
    using (
        owner_github_id = (select public.current_github_id())
        or (team_id is not null and public.is_team_owner(team_id))
    );

-- 다른 테이블과 같은 규약: 기본 권한을 걷고, 로그인 사용자에게 읽기만 준다 (행 범위는 위 정책이 정한다)
revoke all on public.work_reports from anon, authenticated;
grant select on public.work_reports to authenticated;
