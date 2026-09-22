"use server";

/**
 * 계정 단위 동작 — 내보내기와 삭제
 */

import { createHash, randomBytes } from "node:crypto";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient } from "@/lib/supabase-server";

/** 모든 결정을 JSON으로. Server Action은 파일을 돌려줄 수 없어 API 라우트로 보낸다. */
export async function exportMyData(): Promise<void> {
  redirect("/api/export");
}

/**
 * 계정 삭제. accounts 행을 지우면 profiles·decisions·review_events·api_tokens 가 연쇄 삭제된다.
 * auth.users 는 사용자 세션으로 지울 수 없으므로(관리 API 필요) 로그아웃만 한다 —
 * 같은 GitHub로 다시 로그인하면 빈 계정이 새로 만들어진다.
 */
export async function deleteMyAccount(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");

  const confirm = String(form.get("confirm") ?? "").trim();
  if (confirm !== account.github_login) {
    redirect("/settings?error=confirm_mismatch");
  }

  const { error } = await supabase.rpc("delete_my_account");
  if (error) throw new Error(`계정 삭제 실패: ${error.message}`);

  await supabase.auth.signOut();
  redirect("/?deleted=1");
}

// pit/server/tokens.py 와 같은 형식: pit_<32바이트 urlsafe>, DB에는 sha256 해시만
const TOKEN_PREFIX = "pit_";
const TOKEN_RANDOM_BYTES = 32;
const MAX_TOKEN_NAME_CHARS = 60;

/**
 * 로컬 pit 용 토큰 발급. 원문은 이 응답에서 한 번만 보이고, 서버에는 해시만 남는다.
 * Server Action은 값을 화면에 직접 돌려줄 수 없어 쿠키에 잠깐 실어 설정 화면이 읽고 지운다.
 */
export async function issueToken(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");

  const name = String(form.get("name") ?? "").trim().slice(0, MAX_TOKEN_NAME_CHARS) || "local pit";
  const token = TOKEN_PREFIX + randomBytes(TOKEN_RANDOM_BYTES).toString("base64url");
  const tokenHash = createHash("sha256").update(token).digest("hex");

  const { error } = await supabase
    .from("api_tokens")
    .insert({ owner_github_id: account.github_id, name, token_hash: tokenHash });
  if (error) throw new Error(`토큰 발급 실패: ${error.message}`);

  const { cookies } = await import("next/headers");
  (await cookies()).set("pithub_new_token", token, { httpOnly: true, sameSite: "strict", maxAge: 60, path: "/settings" });
  revalidatePath("/settings");
}

export async function revokeToken(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const id = String(form.get("id") ?? "");
  const { error } = await supabase.from("api_tokens").update({ revoked_at: new Date().toISOString() }).eq("id", id);
  if (error) throw new Error(`토큰 폐기 실패: ${error.message}`);
  revalidatePath("/settings");
}
