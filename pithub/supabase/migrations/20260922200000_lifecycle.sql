-- pithub: 생애주기 신호와 검색 인덱스 (D-0007 1단계)
--
-- 기록은 사람이 보지 않은 채 쌓이고 조회된다. 무엇이 쓰였는지(인용), 무엇이 반복됐는지,
-- 무엇이 뒤집혔는지를 신호로 남겨 검색 순위와 원칙 압축의 재료로 삼는다.

create extension if not exists pg_trgm;

alter table public.decisions
    -- get_decision 으로 전체 내용을 가져간 횟수 = 실제로 쓰인 횟수
    add column cited_count int not null default 0,
    add column last_cited_at timestamptz,
    -- 같은 프로젝트에서 며칠 안에 같은 제안이 다시 기록된 횟수 (새 행을 만들지 않고 접는다)
    add column repeat_count int not null default 1,
    -- 이 결정이 예외를 낸 원칙의 id
    add column exception_of text;

alter table public.decisions drop constraint decisions_status_check;
alter table public.decisions add constraint decisions_status_check
    check (status in ('draft', 'confirmed', 'discarded', 'archived'));

-- 한국어는 기본 전문검색이 형태소를 못 자르므로 trigram. ILIKE '%…%' 가 인덱스를 탄다.
create index decisions_situation_trgm on public.decisions using gin (situation gin_trgm_ops);
create index decisions_proposal_trgm on public.decisions using gin (proposal gin_trgm_ops);
create index decisions_quote_trgm on public.decisions using gin (human_quote gin_trgm_ops);
create index decisions_rationale_trgm on public.decisions using gin (rationale gin_trgm_ops);

-- 어떤 검색이 무엇을 돌려주었나. 이후 get_decision 이 used 를 채운다 (A1의 실측).
create table public.citations (
    id bigint generated always as identity primary key,
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,
    query text not null,
    returned_ids text[] not null,
    used_ids text[] not null default '{}',
    client text,
    created_at timestamptz not null default now()
);

create index citations_owner_idx on public.citations (owner_github_id, created_at desc);

alter table public.citations enable row level security;
revoke all on public.citations from anon, authenticated;
grant select on public.citations to authenticated;
create policy citations_select_own on public.citations
    for select to authenticated using (owner_github_id = (select public.current_github_id()));

-- 대체 관계는 정리함에서 사람이 본다. 소유자만 supersedes 를 고칠 수 있다(이미 update grant 에 포함).
