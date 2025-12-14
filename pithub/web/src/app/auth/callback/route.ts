/**
 * GitHub OAuth 콜백 처리
 */

import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/";

  if (code) {
    const cookieStore = await cookies();

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            try {
              cookiesToSet.forEach(({ name, value, options }) =>
                cookieStore.set(name, value, options)
              );
            } catch {
              // Server Component에서 쿠키 설정 실패해도 계속 진행
            }
          },
        },
      }
    );

    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      // GitHub 액세스 토큰을 profiles 테이블에 저장
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (session?.provider_token) {
        // GitHub 토큰 저장 (private repo 접근용)
        await supabase
          .from("profiles")
          .update({ github_access_token: session.provider_token })
          .eq("id", session.user.id);
      }

      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  // 에러 발생 시 홈으로 리다이렉트
  return NextResponse.redirect(`${origin}/?error=auth_callback_error`);
}
