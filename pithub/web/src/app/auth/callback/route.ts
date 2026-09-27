/**
 * GitHub OAuth 콜백 — 코드를 세션으로 바꾼다
 *
 * GitHub 토큰(provider_token)은 어디에도 저장하지 않는다. 로그인에 필요한 것은 신원뿐이다.
 */

import { NextResponse } from "next/server";

import { createServerSupabaseClient } from "@/lib/supabase-server";

// 같은 사이트의 경로만: '/'로 시작하고 '//' 나 '\\' 로 시작하지 않으며, 쿼리(동의 화면의 authorization_id)는 허용한다
const SETTINGS_PATH = "/settings";
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

/**
 * 링크가 통하지 않았을 때 갈 곳. 흔한 원인: 만료·이미 쓴 링크, 요청한 브라우저가 아닌 곳(다른 기기·메신저 안
 * 브라우저)에서 연 링크. 로그인 화면이 코드 입력을 안내한다. 설정에서 로그인 방법을 잇다 실패하면 설정으로
 * (이미 로그인한 사람을 로그인 화면으로 보내면 곧바로 튕겨 이유가 사라진다).
 */
function failureRedirect(origin: string, next: string): string {
  if (next === SETTINGS_PATH) return `${origin}${SETTINGS_PATH}?link_error=1`;
  const retry = new URLSearchParams({ error: "link", next });
  return `${origin}/login?${retry.toString()}`;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const origin = publicOrigin(request);
  const code = searchParams.get("code");
  const requested = searchParams.get("next") ?? "/inbox";
  // 열린 리다이렉트를 막는다: 같은 사이트의 경로만 허용
  const next = SAFE_NEXT.test(requested) ? requested : "/inbox";

  if (!code) {
    if (searchParams.get("error")) {
      return NextResponse.redirect(failureRedirect(origin, next));
    }
    return NextResponse.redirect(`${origin}/?error=missing_code`);
  }

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return NextResponse.redirect(failureRedirect(origin, next));
  }
  // 계정 보장: 지웠다가 다시 온 사람도 계정이 이어지게 (트리거는 첫 가입 때만 돈다)
  const { error: accountError } = await supabase.rpc("ensure_my_account");
  if (accountError) {
    return NextResponse.redirect(`${origin}/?error=account_setup_failed`);
  }
  return NextResponse.redirect(`${origin}${next}`);
}
