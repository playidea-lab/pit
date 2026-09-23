"use server";

/**
 * 결정에 대한 쓰기 — 전부 로그인한 사용자의 세션으로 실행되고 RLS가 소유자를 확인한다.
 * 결정을 새로 만드는 동작은 없다. 그것은 MCP 서버의 몫이다.
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createServerSupabaseClient } from "@/lib/supabase-server";
import type { Verdict } from "@/lib/decisions";

const VERDICTS: readonly Verdict[] = ["approve", "modify", "reject"];
const EDITABLE_TEXT_FIELDS = ["situation", "proposal", "rationale", "human_quote"] as const;
const MAX_TEXT_CHARS = 4000;

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

async function logReview(
  supabase: Awaited<ReturnType<typeof createServerSupabaseClient>>,
  decisionId: string,
  ownerGithubId: number,
  action: "confirmed" | "edited" | "discarded",
  editedFields: string[],
  seconds: number,
) {
  const { error } = await supabase.from("review_events").insert({
    decision_id: decisionId,
    owner_github_id: ownerGithubId,
    action,
    edited_fields: editedFields,
    seconds,
    origin: "web",
  });
  if (error) throw new Error(`검토 기록 실패: ${error.message}`);
}

/** 받은함에서 확정 — 판정을 고쳤거나 글을 고쳤으면 그 사실도 기록한다 */
export async function reviewDecision(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const id = text(form, "id");
  const ownerGithubId = Number(form.get("owner_github_id"));
  const seconds = Number(form.get("seconds")) || 0;
  const command = text(form, "command");

  if (command === "discard") {
    const { error } = await supabase.from("decisions").update({ status: "discarded" }).eq("id", id);
    if (error) throw new Error(`버리기 실패: ${error.message}`);
    await logReview(supabase, id, ownerGithubId, "discarded", [], seconds);
    revalidatePath("/inbox");
    revalidatePath("/decisions");
    redirect("/inbox");
  }

  const { data: current, error: readError } = await supabase
    .from("decisions")
    .select("verdict, situation, proposal, rationale, human_quote")
    .eq("id", id)
    .single();
  if (readError || !current) throw new Error("결정을 찾을 수 없습니다.");

  const update: Record<string, string | null> = { status: "confirmed" };
  const editedFields: string[] = [];

  const verdict = text(form, "verdict");
  if (verdict && VERDICTS.includes(verdict as Verdict) && verdict !== current.verdict) {
    update.verdict = verdict;
    editedFields.push("verdict");
  }
  for (const field of EDITABLE_TEXT_FIELDS) {
    if (!form.has(field)) continue;
    const value = text(form, field).slice(0, MAX_TEXT_CHARS);
    if (value !== current[field]) {
      update[field] = value;
      editedFields.push(field);
    }
  }

  const { error } = await supabase.from("decisions").update(update).eq("id", id);
  if (error) throw new Error(`확정 실패: ${error.message}`);
  await logReview(supabase, id, ownerGithubId, editedFields.length ? "edited" : "confirmed", editedFields, seconds);
  revalidatePath("/inbox");
  revalidatePath("/decisions");
  revalidatePath(`/d/${id}`);
}

/** 팀에서 빼기 — 팀에 보이기 전(3일 유예 안)에만 된다. 보인 뒤에는 DB가 거부한다. */
export async function withdrawFromTeam(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const id = text(form, "id");
  const { error } = await supabase.from("decisions").update({ visibility: "private", team_id: null }).eq("id", id);
  if (error) throw new Error(`팀에서 빼기 실패: ${error.message}`);
  revalidatePath(`/d/${id}`);
  revalidatePath("/inbox");
}

export async function deleteDecision(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const id = text(form, "id");
  const { error } = await supabase.from("decisions").delete().eq("id", id);
  if (error) throw new Error(`삭제 실패: ${error.message}`);
  revalidatePath("/inbox");
  redirect("/inbox");
}

export async function signOut(): Promise<void> {
  const supabase = await createServerSupabaseClient();
  await supabase.auth.signOut();
  redirect("/");
}

const CONFLICT_ACTIONS = ["confirm", "dismiss", "supersede"] as const;

/** 충돌 후보 처리 — 충돌 맞음 / 충돌 아님 / 나중 결정이 먼저 것을 뒤집음 (G5). DB 함수가 권한을 확인한다. */
export async function resolveConflict(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const linkId = Number(form.get("link_id"));
  const action = text(form, "action");
  if (!CONFLICT_ACTIONS.includes(action as (typeof CONFLICT_ACTIONS)[number])) throw new Error("알 수 없는 처리입니다.");
  const { error } = await supabase.rpc("resolve_conflict", { link_id: linkId, action });
  if (error) throw new Error(`충돌 처리 실패: ${error.message}`);
  revalidatePath("/inbox");
}
