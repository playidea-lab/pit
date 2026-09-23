/**
 * GitHub OAuth 콜백 — 코드를 세션으로 바꾼다
 *
 * GitHub 토큰(provider_token)은 어디에도 저장하지 않는다. 로그인에 필요한 것은 신원뿐이다.
 */

import { NextResponse } from "next/server";

import { createServerSupabaseClient } from "@/lib/supabase-server";

// 같은 사이트의 경로만: '/'로 시작하고 '//' 나 '\\' 로 시작하지 않으며, 쿼리(동의 화면의 authorization_id)는 허용한다
const SAFE_NEXT = /^\/(?![/\\])[A-Za-z0-9_\-/.~]*(\?[A-Za-z0-9_\-=&%.~]*)?$/;

/**
 * 사용자가 실제로 접속한 주소. 컨테이너 안에서 request.url 은 http://0.0.0.0:3000/... 이라
 * 그대로 쓰면 로그인 뒤 그 주소로 보내 버린다. 프록시가 넘겨 준 헤더를 우선한다.
 */
function publicOrigin(request: Request): string {
  const url = new URL(request.url);
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? url.host;
  const proto = request.headers.get("x-forwarded-proto") ?? url.protocol.replace(":", "");
  return `${proto}://${host}`;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const origin = publicOrigin(request);
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
