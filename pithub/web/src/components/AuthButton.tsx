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
    return <span className="text-sm text-gray-500">…</span>;
  }

  if (user) {
    const avatarUrl = user.user_metadata?.avatar_url as string | undefined;
    const username = (user.user_metadata?.user_name as string | undefined) ?? "me";
    return (
      <div className="flex items-center gap-3">
        {avatarUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarUrl} alt={username} className="w-7 h-7 rounded-full" />
        )}
        <span className="text-sm text-gray-300">{username}</span>
        <form action={signOut}>
          <button className="px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm">Sign out</button>
        </form>
      </div>
    );
  }

  return (
    <button
      onClick={handleSignIn}
      className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-600 text-sm"
    >
      Sign in with GitHub
    </button>
  );
}
