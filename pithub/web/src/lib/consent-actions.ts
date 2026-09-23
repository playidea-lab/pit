"use server";

/**
 * AI 도구 연결 동의 처리 — Supabase Auth OAuth 2.1 서버에 허용/거절을 알리고 도구로 돌려보낸다
 */

import { redirect } from "next/navigation";

import { createServerSupabaseClient } from "@/lib/supabase-server";

export async function decideConsent(form: FormData): Promise<void> {
  const authorizationId = String(form.get("authorization_id") ?? "");
  const approve = String(form.get("decision") ?? "") === "approve";
  const supabase = await createServerSupabaseClient();
  const { data, error } = approve
    ? await supabase.auth.oauth.approveAuthorization(authorizationId, { skipBrowserRedirect: true })
    : await supabase.auth.oauth.denyAuthorization(authorizationId, { skipBrowserRedirect: true });
  if (error || !data?.redirect_url) throw new Error(`연결 처리 실패: ${error?.message ?? "redirect 없음"}`);
  redirect(data.redirect_url);
}
