/**
 * GitHub OAuth 콜백 — 코드를 세션으로 바꾼다
 *
 * GitHub 토큰(provider_token)은 어디에도 저장하지 않는다. 로그인에 필요한 것은 신원뿐이다.
 */

import { NextResponse } from "next/server";

import { createServerSupabaseClient } from "@/lib/supabase-server";

const SAFE_NEXT = /^\/[A-Za-z0-9_\-/]*$/;

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const requested = searchParams.get("next") ?? "/inbox";
  // 열린 리다이렉트를 막는다: 같은 사이트의 경로만 허용
  const next = SAFE_NEXT.test(requested) ? requested : "/inbox";

  if (!code) {
    return NextResponse.redirect(`${origin}/?error=missing_code`);
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(`${origin}/?error=auth_callback_error`);
  }
  return NextResponse.redirect(`${origin}${next}`);
}
