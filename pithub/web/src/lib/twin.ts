/**
 * 내 트윈 (G6) — 트윈이 기권해 나에게 온 질문, 누가 내 트윈에게 무엇을 물었는지.
 * 질문은 묻은 사람과 트윈 주인만(RLS), 자문 기록은 트윈 주인만 본다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

const TWIN_LIST_LIMIT = 30;

export interface TwinQuestion {
  id: number;
  asker: string;
  situation: string;
  proposal: string;
  confidence: number | null;
  created_at: string;
}

export interface Consult {
  id: number;
  asker: string;
  question: string;
  confidence: number | null;
  abstained: boolean;
  created_at: string;
}

function fail(where: string, error: { message: string } | null): never {
  throw new Error(`${where}: ${error?.message ?? "unknown error"}`);
}

/** github_id → 로그인. 팀원(초대 중 포함)의 계정만 보인다. */
async function loginsOf(supabase: SupabaseClient, ids: number[]): Promise<Map<number, string>> {
  if (ids.length === 0) return new Map();
  const { data } = await supabase.from("accounts").select("github_id, github_login").in("github_id", [...new Set(ids)]);
  return new Map((data ?? []).map((a) => [a.github_id as number, a.github_login as string]));
}

export async function listPendingQuestions(supabase: SupabaseClient, me: number): Promise<TwinQuestion[]> {
  const { data, error } = await supabase
    .from("twin_questions")
    .select("id, asker_github_id, situation, proposal, confidence, created_at")
    .eq("twin_github_id", me)
    .is("answered_at", null)
    .order("created_at", { ascending: false })
    .limit(TWIN_LIST_LIMIT);
  if (error) fail("listPendingQuestions", error);
  const logins = await loginsOf(supabase, (data ?? []).map((q) => q.asker_github_id as number));
  return (data ?? []).map((q) => ({
    id: q.id as number,
    asker: logins.get(q.asker_github_id as number) ?? "동료",
    situation: q.situation as string,
    proposal: q.proposal as string,
    confidence: q.confidence as number | null,
    created_at: q.created_at as string,
  }));
}

export async function listConsults(supabase: SupabaseClient, me: number): Promise<Consult[]> {
  const { data, error } = await supabase
    .from("consult_log")
    .select("id, asker_github_id, question, confidence, abstained, created_at")
    .eq("twin_github_id", me)
    .order("created_at", { ascending: false })
    .limit(TWIN_LIST_LIMIT);
  if (error) fail("listConsults", error);
  const logins = await loginsOf(supabase, (data ?? []).map((c) => c.asker_github_id as number));
  return (data ?? []).map((c) => ({
    id: c.id as number,
    asker: logins.get(c.asker_github_id as number) ?? "동료",
    question: c.question as string,
    confidence: c.confidence as number | null,
    abstained: Boolean(c.abstained),
    created_at: c.created_at as string,
  }));
}
