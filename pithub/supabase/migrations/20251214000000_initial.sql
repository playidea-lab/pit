-- pithub Initial Schema
-- GitHub OAuth 사용자 및 .pit/ 캐시 관리

-- 사용자 프로필 (auth.users 확장)
create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  github_username text unique,
  github_avatar_url text,
  github_access_token text, -- 암호화된 토큰
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- RLS 활성화
alter table public.profiles enable row level security;

-- 프로필 정책: 본인만 조회/수정
create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- 사용자가 등록한 repos
create table if not exists public.repos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade,
  owner text not null,
  name text not null,
  default_branch text default 'main',
  is_private boolean default false,
  last_synced_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(owner, name)
);

-- RLS 활성화
alter table public.repos enable row level security;

-- Repos 정책: public repos는 누구나 조회, private는 본인만
create policy "Anyone can view public repos"
  on public.repos for select
  using (not is_private or auth.uid() = user_id);

create policy "Users can insert own repos"
  on public.repos for insert
  with check (auth.uid() = user_id);

create policy "Users can update own repos"
  on public.repos for update
  using (auth.uid() = user_id);

create policy "Users can delete own repos"
  on public.repos for delete
  using (auth.uid() = user_id);

-- .pit/ 파일 캐시 (GitHub API 레이트 제한 우회)
create table if not exists public.pit_cache (
  id uuid primary key default gen_random_uuid(),
  repo_id uuid references public.repos(id) on delete cascade,
  branch text not null default 'main',
  file_path text not null,
  content jsonb not null,
  sha text, -- GitHub blob SHA (변경 감지용)
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(repo_id, branch, file_path)
);

-- RLS 활성화
alter table public.pit_cache enable row level security;

-- Cache 정책: repo 접근 권한 따름
create policy "Cache follows repo access"
  on public.pit_cache for select
  using (
    exists (
      select 1 from public.repos r
      where r.id = pit_cache.repo_id
      and (not r.is_private or auth.uid() = r.user_id)
    )
  );

create policy "Users can update cache for own repos"
  on public.pit_cache for all
  using (
    exists (
      select 1 from public.repos r
      where r.id = pit_cache.repo_id
      and auth.uid() = r.user_id
    )
  );

-- 채팅 히스토리
create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade,
  repo_id uuid references public.repos(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  model text, -- 사용된 LLM 모델
  metadata jsonb default '{}',
  created_at timestamptz default now()
);

-- RLS 활성화
alter table public.chat_messages enable row level security;

-- Chat 정책: 본인 채팅만 조회
create policy "Users can view own chat messages"
  on public.chat_messages for select
  using (auth.uid() = user_id);

create policy "Users can insert own chat messages"
  on public.chat_messages for insert
  with check (auth.uid() = user_id);

-- 실시간 구독 설정
alter publication supabase_realtime add table public.pit_cache;
alter publication supabase_realtime add table public.chat_messages;

-- 인덱스
create index if not exists idx_repos_owner_name on public.repos(owner, name);
create index if not exists idx_pit_cache_repo_branch on public.pit_cache(repo_id, branch);
create index if not exists idx_chat_messages_user_repo on public.chat_messages(user_id, repo_id);

-- Updated_at 트리거 함수
create or replace function public.handle_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- Updated_at 트리거 적용
create trigger on_profiles_updated
  before update on public.profiles
  for each row execute function public.handle_updated_at();

create trigger on_repos_updated
  before update on public.repos
  for each row execute function public.handle_updated_at();

create trigger on_pit_cache_updated
  before update on public.pit_cache
  for each row execute function public.handle_updated_at();

-- Auth 훅: 새 사용자 등록 시 프로필 생성
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, github_username, github_avatar_url)
  values (
    new.id,
    new.raw_user_meta_data->>'user_name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end;
$$ language plpgsql security definer;

-- 새 사용자 트리거
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
