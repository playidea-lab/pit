/**
 * 결정 데이터 — 타입과 읽기
 *
 * 쓰기는 actions.ts의 Server Action으로만 한다.
 * 모든 읽기는 사용자 세션으로 이루어지고 RLS가 남의 것을 걸러 준다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

export type Verdict = "approve" | "modify" | "reject";
export type DecisionStatus = "draft" | "confirmed" | "discarded";
export type Visibility = "private" | "team" | "friends" | "public";

/** decisions 테이블의 행 (소유자만 보는 열 포함) */
export interface Decision {
  id: string;
  owner_github_id: number;
  status: DecisionStatus;
  visibility: Visibility;
  team_id: string | null;
  origin: "mcp" | "local_extract";
  kind: "verdict" | "choice";
  verdict: Verdict | null;
  reject_kind: "stop" | "redirect" | null;
  situation: string;
  proposal: string;
  options: string[];
  chosen: string | null;
  rationale: string;
  human_quote: string;
  tags: string[];
  supersedes: string[];
  consulted: { github_id: number; decision_id: string; predicted?: string }[];
  decided_at: string;
  created_at: string;
  source: Record<string, string>;
  redactions: Record<string, number>;
}

/** public_decisions 뷰의 행 — 출처·가림 내역이 없다 */
export interface PublicDecision {
  id: string;
  github_login: string;
  avatar_url: string | null;
  kind: "verdict" | "choice";
  verdict: Verdict | null;
  reject_kind: "stop" | "redirect" | null;
  situation: string;
  proposal: string;
  options: string[];
  chosen: string | null;
  rationale: string;
  human_quote: string;
  tags: string[];
  supersedes: string[];
  decided_at: string;
}

export interface Account {
  github_id: number;
  github_login: string;
  avatar_url: string | null;
}

export const TRIAGE_PAGE_SIZE = 60;
export const TIMELINE_PAGE_SIZE = 50;
export const WEEKLY_SAMPLE_SIZE = 5;

function fail(where: string, error: { message: string } | null): never {
  throw new Error(`${where}: ${error?.message ?? "unknown error"}`);
}

/** 로그인한 사용자의 계정 (profile → account). 없으면 null. */
export async function getMyAccount(supabase: SupabaseClient): Promise<Account | null> {
  const { data, error } = await supabase
    .from("profiles")
    .select("account:accounts(github_id, github_login, avatar_url)")
    .maybeSingle();
  if (error) fail("getMyAccount", error);
  const account = data?.account as Account | Account[] | null | undefined;
  return Array.isArray(account) ? (account[0] ?? null) : (account ?? null);
}

/** 아직 사람이 확인하지 않은 기록 전부 (정리함·표본의 재료) */
export async function listUnverified(supabase: SupabaseClient): Promise<Decision[]> {
  const { data, error } = await supabase
    .from("decisions")
    .select("*")
    .eq("status", "draft")
    .order("decided_at", { ascending: false })
    .limit(TRIAGE_PAGE_SIZE * 4);
  if (error) fail("listUnverified", error);
  return (data ?? []) as Decision[];
}

/** 정리함에 올릴 것: 거부·수정 판정, 가림이 일어난 것. 승인은 그냥 기록으로 둔다. */
const VERDICT_WORDS = /(거부|기각|폐기|승인|채택|확정|거절|반려|철회|rejected|approved|dropped|adopted)/;

/** 상황·제안에 판정이 새어 있으면 트윈 평가의 입력에 정답이 들어간 것이다 */
export function leaksVerdict(decision: Pick<Decision, "situation" | "proposal">): boolean {
  return VERDICT_WORDS.test(decision.situation) || VERDICT_WORDS.test(decision.proposal);
}

export function needsAttention(decision: Decision): boolean {
  const redacted = Object.values(decision.redactions).some((n) => n > 0);
  return (
    decision.verdict === "reject" ||
    decision.verdict === "modify" ||
    redacted ||
    decision.supersedes.length > 0 ||
    decision.tags.includes("principle") ||
    leaksVerdict(decision)
  );
}

/** 이번 주의 표본 — 같은 주에는 같은 5건이 나오도록 id와 주차로 결정적으로 고른다 */
export function weeklySample(decisions: Decision[], now: Date = new Date()): Decision[] {
  const week = `${now.getUTCFullYear()}-${Math.floor((now.getTime() / 86400000 + 4) / 7)}`;
  const score = (id: string) => {
    let h = 2166136261;
    for (const ch of `${id}:${week}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0;
    return h;
  };
  return [...decisions].sort((a, b) => score(a.id) - score(b.id)).slice(0, WEEKLY_SAMPLE_SIZE);
}

export async function listMyDecisions(
  supabase: SupabaseClient,
  filter: { verdict?: Verdict; text?: string; unverifiedOnly?: boolean },
): Promise<Decision[]> {
  let query = supabase
    .from("decisions")
    .select("*")
    .neq("status", "discarded")
    .order("decided_at", { ascending: false })
    .limit(TIMELINE_PAGE_SIZE);
  if (filter.unverifiedOnly) query = query.eq("status", "draft");
  if (filter.verdict) query = query.eq("verdict", filter.verdict);
  if (filter.text) {
    const needle = `%${filter.text.replace(/[%_]/g, "")}%`;
    query = query.or(
      ["situation", "proposal", "rationale", "human_quote"].map((c) => `${c}.ilike.${needle}`).join(","),
    );
  }
  const { data, error } = await query;
  if (error) fail("listMyDecisions", error);
  return (data ?? []) as Decision[];
}

export async function getMyDecision(supabase: SupabaseClient, id: string): Promise<Decision | null> {
  const { data, error } = await supabase.from("decisions").select("*").eq("id", id).maybeSingle();
  if (error) fail("getMyDecision", error);
  return (data as Decision | null) ?? null;
}

export async function listPublicDecisions(
  supabase: SupabaseClient,
  handle: string,
  verdict?: Verdict,
): Promise<PublicDecision[]> {
  let query = supabase
    .from("public_decisions")
    .select("*")
    .eq("github_login", handle)
    .order("decided_at", { ascending: false })
    .limit(TIMELINE_PAGE_SIZE);
  if (verdict) query = query.eq("verdict", verdict);
  const { data, error } = await query;
  if (error) fail("listPublicDecisions", error);
  return (data ?? []) as PublicDecision[];
}

export async function getPublicDecision(
  supabase: SupabaseClient,
  id: string,
): Promise<PublicDecision | null> {
  const { data, error } = await supabase.from("public_decisions").select("*").eq("id", id).maybeSingle();
  if (error) fail("getPublicDecision", error);
  return (data as PublicDecision | null) ?? null;
}
