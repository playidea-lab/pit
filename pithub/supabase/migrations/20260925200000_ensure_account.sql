-- pithub: 로그인할 때마다 계정을 보장한다 (재가입 구멍 막기)
--
-- 계정은 인증 서버가 identity 를 처음 만들 때 트리거로 생긴다. 그런데 계정을 지운 사람이 같은 GitHub·이메일로
-- 다시 로그인하면 identity 는 이미 있어 트리거가 돌지 않고, profile 이 없어 "계정 없음" 상태가 된다.
-- 웹 로그인 콜백이 이 함수를 불러, profile 이 없으면 만들거나(떠난 계정이면 되살려) 잇는다.

create function public.ensure_my_account() returns bigint
language plpgsql security definer set search_path = ''
as $$
declare
    uid uuid := auth.uid();
    existing bigint;
    ident record;
    account bigint;
    handle text;
begin
    if uid is null then
        raise exception 'not signed in' using errcode = 'insufficient_privilege';
    end if;
    select github_id into existing from public.profiles where id = uid;
    if existing is not null then
        return existing;
    end if;

    -- GitHub identity 가 있으면 그 숫자 id — 떠난 계정 행이 남아 있으면 되살린다
    select * into ident from auth.identities where user_id = uid and provider = 'github' limit 1;
    if found then
        account := ident.provider_id::bigint;
        insert into public.accounts (github_id, github_login, avatar_url)
        values (account,
                coalesce(ident.identity_data ->> 'user_name', ident.identity_data ->> 'preferred_username', ident.provider_id),
                ident.identity_data ->> 'avatar_url')
        on conflict (github_id) do update set deleted_at = null, updated_at = now();
    else
        -- 이메일(또는 그 밖의 방식): 새 음수 번호. 지운 계정은 결정이 남았어도 다른 번호다 — 이메일은 되살릴 근거가 없다.
        select * into ident from auth.identities where user_id = uid limit 1;
        account := -nextval('public.email_account_seq');
        handle := lower(regexp_replace(split_part(coalesce(ident.identity_data ->> 'email', ''), '@', 1), '[^a-zA-Z0-9._-]', '', 'g'));
        if coalesce(handle, '') = '' then
            handle := 'user';
        end if;
        if exists (select 1 from public.accounts where github_login = handle) then
            handle := handle || '-' || abs(account)::text;
        end if;
        insert into public.accounts (github_id, github_login) values (account, handle);
    end if;
    insert into public.profiles (id, github_id) values (uid, account) on conflict (id) do nothing;
    return account;
end;
$$;

revoke all on function public.ensure_my_account() from public;
grant execute on function public.ensure_my_account() to authenticated;
