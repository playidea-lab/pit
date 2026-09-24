"use server";

/**
 * 결정에 대한 쓰기 — 전부 로그인한 사용자의 세션으로 실행되고 RLS가 소유자를 확인한다.
 * 결정을 새로 만드는 것은 MCP 서버의 몫이다. 예외는 사람이 직접 쓰는 원칙·트윈 질문의 답(DB 함수가 만든다).
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createServerSupabaseClient } from "@/lib/supabase-server";
import type { Verdict } from "@/lib/decisions";

const VERDICTS: readonly Verdict[] = ["approve", "modify", "reject"];
const EDITABLE_TEXT_FIELDS = ["situation", "proposal", "rationale", "human_quote"] as const;
const MAX_TEXT_CHARS = 4000;
const MAX_TOPIC_NAME_CHARS = 120;

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

/** 반복된 판단을 한 줄 원칙으로 압축하거나, 원칙이 아니라고 넘긴다 (그래프 G) */
export async function curatePrinciple(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const node = text(form, "node_id");
  const verdict = text(form, "verdict");
  if (!VERDICTS.includes(verdict as Verdict)) throw new Error("알 수 없는 판정입니다.");
  if (text(form, "action") === "dismiss") {
    const { error } = await supabase.rpc("dismiss_principle", { node, dismissed_verdict: verdict });
    if (error) throw new Error(`원칙 후보 넘기기 실패: ${error.message}`);
  } else {
    const statement = text(form, "statement").slice(0, MAX_TEXT_CHARS);
    if (!statement) throw new Error("원칙을 한 줄로 적어 주세요.");
    const { error } = await supabase.rpc("compress_into_principle", { node, principle_verdict: verdict, statement });
    if (error) throw new Error(`원칙 만들기 실패: ${error.message}`);
  }
  revalidatePath("/inbox");
}

/** 같은 주제입니까? — 합치기(keep 에 drop 을 합치고 drop 이름은 별칭으로) 또는 다른 주제 (G3) */
export async function curateNodes(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const keep = text(form, "keep_id");
  const drop = text(form, "drop_id");
  const { error } =
    text(form, "action") === "merge"
      ? await supabase.rpc("merge_nodes", { keep, drop_node: drop })
      : await supabase.rpc("dismiss_node_merge", { node_x: keep, node_y: drop });
  if (error) throw new Error(`주제 정리 실패: ${error.message}`);
  revalidatePath("/inbox");
}

const TWIN_VERDICTS = ["approve", "modify", "reject"] as const;

/** 트윈이 기권해 나에게 온 질문에 답한다 — 답은 내 확인된 결정이 되어 다음 판정의 근거가 된다 (G6) */
export async function answerTwinQuestion(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const questionId = Number(form.get("question_id"));
  const verdict = text(form, "verdict");
  const quote = text(form, "quote").slice(0, MAX_TEXT_CHARS);
  if (!TWIN_VERDICTS.includes(verdict as (typeof TWIN_VERDICTS)[number]) || !quote) {
    throw new Error("판정과 한 줄 답이 필요합니다.");
  }
  const { error } = await supabase.rpc("answer_twin_question", {
    question_id: questionId,
    answer_verdict: verdict,
    answer_quote: quote,
  });
  if (error) throw new Error(`답하기 실패: ${error.message}`);
  revalidatePath("/twin");
}

/** 트윈의 답 채점 — "당신이라면?" 주인의 판정이 kNN·JEV 두 판정기의 채점 기준이 된다 */
export async function rateTwinAnswer(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const verdict = text(form, "verdict");
  if (!TWIN_VERDICTS.includes(verdict as (typeof TWIN_VERDICTS)[number])) throw new Error("판정을 골라 주세요.");
  const { error } = await supabase.rpc("rate_twin_answer", { consult_id: Number(form.get("consult_id")), verdict });
  if (error) throw new Error(`채점 실패: ${error.message}`);
  revalidatePath("/twin");
}

/** 주제에 다른 이름 붙이기 — 언어가 다른 같은 뜻을 한 주제로 (그래프 C) */
export async function addTopicAlias(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const node = text(form, "node_id");
  const alias = text(form, "alias").slice(0, MAX_TOPIC_NAME_CHARS);
  if (!alias) return;
  const { error } = await supabase.rpc("add_node_alias", { node, alias });
  if (error) throw new Error(`다른 이름 추가 실패: ${error.message}`);
  revalidatePath(`/topic/${node}`);
}

/** 이 주제를 다른 주제에 합치기 — 이 주제의 결정이 모두 옮겨가고, 이 이름은 별칭이 된다 */
export async function mergeTopicInto(form: FormData): Promise<void> {
  const supabase = await createServerSupabaseClient();
  const drop = text(form, "node_id");
  const keep = text(form, "into");
  if (!keep) return;
  const { error } = await supabase.rpc("merge_nodes", { keep, drop_node: drop });
  if (error) throw new Error(`합치기 실패: ${error.message}`);
  revalidatePath("/topics");
  redirect(`/topic/${keep}`);
}
