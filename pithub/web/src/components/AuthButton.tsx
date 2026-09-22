"use client";

import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";

import { createClient, isSupabaseConfigured } from "@/lib/supabase";
import { signOut } from "@/lib/actions";

// 로그인에 필요한 것은 신원뿐이다. 저장소 권한(repo)은 요구하지 않는다.
const GITHUB_SCOPES = "read:user";

export default function AuthButton() {
  const [user, setUser] = useState<User | null>(null);
  const configured = isSupabaseConfigured();
  // 설정이 없으면 확인할 것도 없다 — 초기값에서 결정해 effect 안의 동기 setState를 피한다
  const [loading, setLoading] = useState(configured);

  useEffect(() => {
    const supabase = createClient();
    if (!supabase) return;
    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user);
      setLoading(false);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => setUser(session?.user ?? null));
    return () => subscription.unsubscribe();
  }, []);

  if (!configured) return null;

  const handleSignIn = async () => {
    const supabase = createClient();
    if (!supabase) return;
    await supabase.auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: `${window.location.origin}/auth/callback`, scopes: GITHUB_SCOPES },
    });
  };

  if (loading) {
    return <span className="faint text-sm">…</span>;
  }

  if (user) {
    const avatarUrl = user.user_metadata?.avatar_url as string | undefined;
    const username = (user.user_metadata?.user_name as string | undefined) ?? "me";
    return (
      <div className="flex items-center gap-3">
        {avatarUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt={username} className="h-7 w-7 rounded-full border border-border" />
        )}
        <span className="muted text-sm">{username}</span>
        <form action={signOut}>
          <button className="btn btn-ghost h-8 px-2.5">로그아웃</button>
        </form>
      </div>
    );
  }

  return (
    <button onClick={handleSignIn} className="btn btn-primary">
      <GitHubMark />
      GitHub로 로그인
    </button>
  );
}

function GitHubMark() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
