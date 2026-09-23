-- pithub: 이메일 로그인 계정 (2026-09-25 사용자 요청)
--
-- 계정 번호(accounts.github_id)는 그대로 모든 결정·팀·권한의 열쇠다. GitHub 사용자는 GitHub 숫자 id(양수),
-- 이메일 사용자는 겹치지 않도록 음수 번호를 받는다. 열 이름은 역사적 이유로 github_id 로 남는다.
-- 이메일로 가입한 사람의 이름(github_login)은 이메일 앞부분이고, 겹치면 번호를 붙인다.

create sequence public.email_account_seq;

create function public.handle_email_identity() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
    account bigint;
    handle text;
begin
    if new.provider <> 'email' then
        return new;
    end if;
    -- 이미 계정이 이어진 사용자(예: GitHub로 먼저 가입)면 새로 만들지 않는다
    if exists (select 1 from public.profiles where id = new.user_id) then
        return new;
    end if;
    account := -nextval('public.email_account_seq');
    handle := lower(regexp_replace(split_part(coalesce(new.identity_data ->> 'email', ''), '@', 1), '[^a-zA-Z0-9._-]', '', 'g'));
    if handle = '' then
        handle := 'user';
    end if;
    if exists (select 1 from public.accounts where github_login = handle) then
        handle := handle || '-' || abs(account)::text;
    end if;
    insert into public.accounts (github_id, github_login) values (account, handle);
    insert into public.profiles (id, github_id) values (new.user_id, account) on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_email_identity_created
    after insert on auth.identities
    for each row execute function public.handle_email_identity();

-- GitHub로 나중에 이어 붙였을 때: 이미 이메일 계정이 있으면 GitHub 계정 행은 만들되 profile 은 이메일 계정에 남는다
-- (handle_github_identity 의 "on conflict (id) do nothing" 이 그 역할을 한다)
