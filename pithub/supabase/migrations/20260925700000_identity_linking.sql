-- pithub: 로그인 방법 잇기 (2026-09-25)
--
-- 한 사람 = 인증 사용자 하나 = 계정 하나. 이메일로 가입한 사람이 설정에서 GitHub 를 이어 붙이면
-- (Supabase manual linking) 같은 인증 사용자에 GitHub identity 가 추가된다. 그때 GitHub 번호로
-- 새 계정 행을 만들면 아무 결정도 없는 빈 계정이 생기고, 트윈이 GitHub 이름으로 그 빈 계정을 찾는다.
-- → 이미 계정이 있는 사용자면 새 계정을 만들지 않고, 비어 있는 프로필 사진만 채운다.

create or replace function public.handle_github_identity() returns trigger
language plpgsql security definer set search_path = ''
as $$
declare
    existing bigint;
begin
    if new.provider <> 'github' then
        return new;
    end if;

    select github_id into existing from public.profiles where id = new.user_id;
    if existing is not null then
        update public.accounts
           set avatar_url = coalesce(avatar_url, new.identity_data ->> 'avatar_url'), updated_at = now()
         where github_id = existing;
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
