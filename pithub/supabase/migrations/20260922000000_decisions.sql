-- pithub: 개인 결정 저장소
--
-- 신원의 열쇠는 GitHub 숫자 id다. MCP 커넥터로 먼저 들어온 사람은 아직 Supabase 계정이
-- 없을 수 있으므로, 결정은 accounts(github_id)에 묶는다. 웹에 처음 로그인하면
-- auth.identities 트리거가 profile을 만들고 같은 github_id로 이어 준다.
--
-- 권한 원칙: 웹은 사용자 세션으로만 읽고 쓰며 RLS가 집행한다. MCP 서버만 service_role을 쓴다.
-- 공개 읽기는 public_decisions 뷰로만 — 출처(source)와 가림 내역은 뷰에 없다.

-- ---------------------------------------------------------------------------
-- 계정
-- ---------------------------------------------------------------------------

create table public.accounts (
    github_id bigint primary key,
    github_login text not null,
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    github_id bigint not null unique references public.accounts (github_id) on delete cascade,
    created_at timestamptz not null default now()
);

-- 현재 세션 사용자의 GitHub id. RLS 정책이 profiles를 직접 읽으면 정책끼리 재귀하므로 함수로 뺀다.
create function public.current_github_id() returns bigint
language sql stable security definer set search_path = ''
as $$
    select github_id from public.profiles where id = (select auth.uid())
$$;

-- GitHub identity가 생길 때 계정과 profile을 만든다.
-- auth.users.raw_user_meta_data 는 사용자가 고칠 수 있으므로 쓰지 않는다.
-- auth.identities.provider_id 는 인증 서버만 쓴다.
create function public.handle_github_identity() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
    if new.provider <> 'github' then
        return new;
    end if;

    insert into public.accounts (github_id, github_login, avatar_url)
    values (
        new.provider_id::bigint,
        coalesce(new.identity_data ->> 'user_name', new.identity_data ->> 'preferred_username', new.provider_id),
        new.identity_data ->> 'avatar_url'
    )
    on conflict (github_id) do update
        set github_login = excluded.github_login,
            avatar_url = excluded.avatar_url,
            updated_at = now();

    insert into public.profiles (id, github_id)
    values (new.user_id, new.provider_id::bigint)
    on conflict (id) do nothing;

    return new;
end;
$$;

create trigger on_github_identity_created
    after insert on auth.identities
    for each row execute function public.handle_github_identity();

-- ---------------------------------------------------------------------------
-- 결정
-- ---------------------------------------------------------------------------

create table public.decisions (
    id text primary key,
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,

    status text not null default 'draft' check (status in ('draft', 'confirmed', 'discarded')),
    visibility text not null default 'private' check (visibility in ('private', 'public')),
    origin text not null check (origin in ('mcp', 'local_extract')),

    kind text not null check (kind in ('verdict', 'choice')),
    verdict text check (verdict in ('approve', 'modify', 'reject')),
    reject_kind text check (reject_kind in ('stop', 'redirect')),
    situation text not null default '',
    proposal text not null default '',
    options jsonb not null default '[]'::jsonb,
    chosen text,
    rationale text not null default '',
    human_quote text not null default '',
    tags text[] not null default '{}',
    supersedes text[] not null default '{}',

    decided_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    -- 비공개 열: 어느 도구·기기·세션에서 왔는지, 무엇을 가렸는지
    source jsonb not null default '{}'::jsonb,
    extractor jsonb not null default '{}'::jsonb,
    review jsonb,
    redactions jsonb not null default '{}'::jsonb,
    -- 같은 사람이 같은 날 같은 (제안 + 인용)을 다시 보내도 한 번만 저장한다
    dedupe_key text not null,

    unique (owner_github_id, dedupe_key),
    -- 판정형 결정에는 판정이, 선택형 결정에는 고른 답이 있어야 한다
    check ((kind = 'verdict' and verdict is not null) or (kind = 'choice' and chosen is not null)),
    -- 확정되지 않은 결정은 공개할 수 없다
    constraint decisions_unconfirmed_private_check check (visibility = 'private' or status = 'confirmed')
);

create index decisions_owner_status_idx on public.decisions (owner_github_id, status, decided_at desc);
create index decisions_public_idx on public.decisions (owner_github_id, decided_at desc)
    where status = 'confirmed' and visibility = 'public';

create table public.review_events (
    id bigint generated always as identity primary key,
    -- 버린 결정은 지워질 수 있으므로 외래키를 걸지 않는다 (품질 통계는 남아야 한다)
    decision_id text not null,
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,
    action text not null check (action in ('confirmed', 'edited', 'discarded')),
    edited_fields text[] not null default '{}',
    seconds real not null default 0,
    origin text not null,
    created_at timestamptz not null default now()
);

create index review_events_owner_idx on public.review_events (owner_github_id, created_at desc);

create table public.api_tokens (
    id uuid primary key default gen_random_uuid(),
    owner_github_id bigint not null references public.accounts (github_id) on delete cascade,
    name text not null,
    -- 토큰 원문은 저장하지 않는다. 발급 직후 한 번만 보여 준다.
    token_hash text not null unique,
    created_at timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);

create function public.touch_updated_at() returns trigger
language plpgsql set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger decisions_touch_updated_at
    before update on public.decisions
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 접근 권한
-- ---------------------------------------------------------------------------

alter table public.accounts enable row level security;
alter table public.profiles enable row level security;
alter table public.decisions enable row level security;
alter table public.review_events enable row level security;
alter table public.api_tokens enable row level security;

-- 기본 권한에 기대지 않고 명시한다. anon에게는 테이블 권한을 주지 않는다.
revoke all on public.accounts, public.profiles, public.decisions, public.review_events, public.api_tokens
    from anon, authenticated;

grant select on public.accounts, public.profiles to authenticated;
grant select, delete on public.decisions to authenticated;
-- 사람이 고칠 수 있는 것은 검토 대상 열뿐이다. 출처(origin, source, extractor)와 id, 소유자, 중복 키는
-- 고칠 수 없다 — MCP 기록을 원문 추출과 대조하는 감사가 이 값들에 기대기 때문이다.
grant update (
    status, visibility, verdict, reject_kind, situation, proposal, chosen,
    rationale, human_quote, tags, supersedes, review
) on public.decisions to authenticated;
grant select, insert on public.review_events to authenticated;
grant select, insert, update on public.api_tokens to authenticated;

create policy accounts_select_own on public.accounts
    for select to authenticated
    using (github_id = (select public.current_github_id()));

create policy profiles_select_own on public.profiles
    for select to authenticated
    using (id = (select auth.uid()));

-- 결정은 MCP 서버(service_role)와 로컬 push API만 만든다. 웹 사용자는 자기 것을 읽고 고치고 지운다.
create policy decisions_select_own on public.decisions
    for select to authenticated
    using (owner_github_id = (select public.current_github_id()));

create policy decisions_update_own on public.decisions
    for update to authenticated
    using (owner_github_id = (select public.current_github_id()))
    with check (owner_github_id = (select public.current_github_id()));

create policy decisions_delete_own on public.decisions
    for delete to authenticated
    using (owner_github_id = (select public.current_github_id()));

create policy review_events_select_own on public.review_events
    for select to authenticated
    using (owner_github_id = (select public.current_github_id()));

create policy review_events_insert_own on public.review_events
    for insert to authenticated
    with check (owner_github_id = (select public.current_github_id()));

create policy api_tokens_select_own on public.api_tokens
    for select to authenticated
    using (owner_github_id = (select public.current_github_id()));

create policy api_tokens_insert_own on public.api_tokens
    for insert to authenticated
    with check (owner_github_id = (select public.current_github_id()));

create policy api_tokens_update_own on public.api_tokens
    for update to authenticated
    using (owner_github_id = (select public.current_github_id()))
    with check (owner_github_id = (select public.current_github_id()));

-- ---------------------------------------------------------------------------
-- 공개 읽기 — 로그인하지 않은 사람도 볼 수 있는 유일한 통로
-- ---------------------------------------------------------------------------

-- 뷰 소유자 권한으로 실행되어 RLS를 지나친다. 그래서 조건과 열 목록이 곧 공개 범위다.
-- source, extractor, review, redactions, dedupe_key 는 여기에 없다.
create view public.public_decisions
with (security_invoker = false)
as
select
    d.id,
    a.github_login,
    a.avatar_url,
    d.kind,
    d.verdict,
    d.reject_kind,
    d.situation,
    d.proposal,
    d.options,
    d.chosen,
    d.rationale,
    d.human_quote,
    d.tags,
    d.supersedes,
    d.decided_at
from public.decisions d
join public.accounts a on a.github_id = d.owner_github_id
where d.status = 'confirmed' and d.visibility = 'public';

grant select on public.public_decisions to anon, authenticated;

-- ---------------------------------------------------------------------------
-- 계정 삭제 — 본인 것만, 연쇄로 결정·검토 이력·토큰까지
-- ---------------------------------------------------------------------------

create function public.delete_my_account() returns void
language plpgsql security definer set search_path = ''
as $$
declare
    my_github_id bigint := public.current_github_id();
begin
    if my_github_id is null then
        raise exception 'not signed in' using errcode = '28000';
    end if;
    delete from public.accounts where github_id = my_github_id;
end;
$$;

revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;
