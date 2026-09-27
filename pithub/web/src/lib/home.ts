/**
 * 로그인한 홈의 숫자들 — 시작 체크리스트와 내 현황. 전부 사용자 세션(RLS)으로 읽는다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import { listUnverified, needsAttention, weeklySample, type Account } from "@/lib/decisions";
import { listMyInvites, listMyTeams, type Team, type TeamInvite } from "@/lib/teams";
import { countPendingQuestions } from "@/lib/twin";

const DAYS_IN_WEEK = 7;
const MS_PER_DAY = 86_400_000;

export interface HomeData {
  teams: Team[];
  invites: TeamInvite[];
  thisWeek: number;
  unverified: number;
  recorded: number;
  searched: number;
  twinQuestions: number;
}

function weekAgoIso(): string {
  return new Date(Date.now() - DAYS_IN_WEEK * MS_PER_DAY).toISOString();
}

async function count(query: PromiseLike<{ count: number | null; error: { message: string } | null }>, where: string) {
  const { count: n, error } = await query;
  if (error) throw new Error(`${where}: ${error.message}`);
  return n ?? 0;
}

/** 정리함이 실제로 보여 주는 건수 (표본 + 봐 둘 만한 것) — 전체 초안 수는 할 일이 아니다 */
async function inboxCount(supabase: SupabaseClient): Promise<number> {
  const drafts = await listUnverified(supabase);
  const sample = new Set(weeklySample(drafts).map((d) => d.id));
  return sample.size + drafts.filter((d) => needsAttention(d) && !sample.has(d.id)).length;
}

export async function loadHome(supabase: SupabaseClient, account: Account): Promise<HomeData> {
  const head = { count: "exact" as const, head: true };
  const [teams, invites, thisWeek, unverified, recorded, searched, twinQuestions] = await Promise.all([
    listMyTeams(supabase, account.github_id),
    listMyInvites(supabase, account.github_id),
    count(supabase.from("decisions").select("id", head).neq("status", "discarded").gte("decided_at", weekAgoIso()), "thisWeek"),
    inboxCount(supabase),
    count(supabase.from("decisions").select("id", head).eq("origin", "mcp"), "recorded"),
    count(supabase.from("citations").select("id", head), "searched"),
    countPendingQuestions(supabase, account.github_id),
  ]);
  return { teams, invites, thisWeek, unverified, recorded, searched, twinQuestions };
}
