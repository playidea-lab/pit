/**
 * 팀 데이터 — 타입과 읽기 (D-0008)
 *
 * 쓰기는 team-actions.ts의 Server Action으로만 한다.
 * 팀원이 읽는 결정은 decisions 가 아니라 team_decisions 뷰다 — 출처·가림 내역이 없는 열만 있다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import type { SharedDecision } from "@/lib/decisions";

export const TEAM_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,38}$/;
const TEAM_TIMELINE_SIZE = 50;

export interface Team {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  /** 외부 판정기(JEV)에 팀 결정을 보내도 된다고 소유자가 동의한 시각 (D-0009 §7) */
  external_judge_consent_at?: string | null;
}

export interface TeamMember {
  team_id: string;
  github_id: number;
  role: "owner" | "member";
  accepted_at: string | null;
  /** 본인과 같으면 가입 요청(소유자가 승인), 다르면 초대(본인이 수락) */
  invited_by: number | null;
  github_login: string;
  avatar_url: string | null;
}

/** 초대장 또는 내가 보낸 가입 요청 */
export interface TeamInvite {
  team: Team;
  invited_by_login: string | null;
  /** 팀 주소로 기록하다 생긴 가입 요청 — 소유자 승인 대기 */
  requested_by_me: boolean;
}

export function isJoinRequest(member: Pick<TeamMember, "github_id" | "accepted_at" | "invited_by">): boolean {
  return !member.accepted_at && member.invited_by === member.github_id;
}

/** team_decisions 뷰의 행 */
export interface TeamDecision extends SharedDecision {
  owner_github_id: number;
  /** 작성자가 계정을 지웠다 — 퇴사자의 판단 */
  departed: boolean;
  /** 사람이 확인했는가 (아니면 3일 유예가 지나 자동으로 보인 것) */
  verified: boolean;
  team_id: string;
  team_slug: string;
  consulted: { github_id: number; decision_id: string; predicted?: string }[];
  cited_count: number;
}

function fail(where: string, error: { message: string } | null): never {
  throw new Error(`${where}: ${error?.message ?? "unknown error"}`);
}

interface MembershipRow {
  team_id: string;
  accepted_at: string | null;
  invited_by: number | null;
  teams: Team | Team[] | null;
}

function one<T>(value: T | T[] | null | undefined): T | null {
  return Array.isArray(value) ? (value[0] ?? null) : (value ?? null);
}

/** 내가 속했거나 초대받은 팀 — RLS가 그 둘만 돌려준다 */
async function listMemberships(supabase: SupabaseClient, githubId: number): Promise<MembershipRow[]> {
  const { data, error } = await supabase
    .from("team_members")
    .select("team_id, accepted_at, invited_by, teams(id, slug, name, created_at)")
    .eq("github_id", githubId)
    .order("joined_at", { ascending: false });
  if (error) fail("listMemberships", error);
  return (data ?? []) as unknown as MembershipRow[];
}

export async function listMyTeams(supabase: SupabaseClient, githubId: number): Promise<Team[]> {
  const rows = await listMemberships(supabase, githubId);
  return rows.filter((r) => r.accepted_at).flatMap((r) => (one(r.teams) ? [one(r.teams) as Team] : []));
}

export async function listMyInvites(supabase: SupabaseClient, githubId: number): Promise<TeamInvite[]> {
  const rows = (await listMemberships(supabase, githubId)).filter((r) => !r.accepted_at);
  if (rows.length === 0) return [];
  const inviterIds = rows.flatMap((r) => (r.invited_by ? [r.invited_by] : []));
  const { data: inviters } = await supabase.from("accounts").select("github_id, github_login").in("github_id", inviterIds);
  const loginOf = new Map((inviters ?? []).map((a) => [a.github_id as number, a.github_login as string]));
  return rows.flatMap((r) => {
    const team = one(r.teams);
    if (!team) return [];
    const requested = r.invited_by === githubId;
    return [{ team, invited_by_login: requested || !r.invited_by ? null : (loginOf.get(r.invited_by) ?? null), requested_by_me: requested }];
  });
}

/** slug로 팀 하나 — 구성원이거나 초대받은 사람에게만 보인다 */
export async function getTeamBySlug(supabase: SupabaseClient, slug: string): Promise<Team | null> {
  const { data, error } = await supabase.from("teams").select("*").eq("slug", slug).maybeSingle();
  if (error) fail("getTeamBySlug", error);
  return (data as Team | null) ?? null;
}

export async function listTeamMembers(supabase: SupabaseClient, teamId: string): Promise<TeamMember[]> {
  const { data, error } = await supabase
    .from("team_members")
    // accounts 로 가는 외래키가 둘(github_id · invited_by)이라 어느 것인지 명시한다
    .select("team_id, github_id, role, accepted_at, invited_by, accounts!team_members_github_id_fkey(github_login, avatar_url)")
    .eq("team_id", teamId)
    .order("joined_at", { ascending: true });
  if (error) fail("listTeamMembers", error);
  type AccountCols = { github_login: string; avatar_url: string | null };
  return (data ?? []).map((row) => {
    const account = one(row.accounts as unknown as AccountCols | AccountCols[] | null);
    return {
      team_id: row.team_id as string,
      github_id: row.github_id as number,
      role: row.role as TeamMember["role"],
      accepted_at: row.accepted_at as string | null,
      invited_by: row.invited_by as number | null,
      github_login: account?.github_login ?? `#${row.github_id}`,
      avatar_url: account?.avatar_url ?? null,
    };
  });
}

/** 팀에 확정된 결정 (본인 것 포함). 수락 전에는 빈 목록이다. */
export async function listTeamDecisions(supabase: SupabaseClient, teamId: string): Promise<TeamDecision[]> {
  const { data, error } = await supabase
    .from("team_decisions")
    .select("*")
    .eq("team_id", teamId)
    .order("decided_at", { ascending: false })
    .limit(TEAM_TIMELINE_SIZE);
  if (error) fail("listTeamDecisions", error);
  return (data ?? []) as TeamDecision[];
}

export async function getTeamDecision(supabase: SupabaseClient, id: string): Promise<TeamDecision | null> {
  const { data, error } = await supabase.from("team_decisions").select("*").eq("id", id).maybeSingle();
  if (error) fail("getTeamDecision", error);
  return (data as TeamDecision | null) ?? null;
}

/** 개인 커넥터 주소(…/mcp)에서 팀 커넥터 주소(…/t/<slug>/mcp)를 만든다 */
export function teamMcpUrl(personalMcpUrl: string, slug: string): string {
  return personalMcpUrl.replace(/\/mcp\/?$/, `/t/${slug}/mcp`);
}

/** 떠난 사람들 — 팀 결정 중 작성자가 계정을 지운 것을 사람별로 묶는다 */
export function departedAuthors(decisions: TeamDecision[]): { github_id: number; github_login: string; count: number }[] {
  const byId = new Map<number, { github_id: number; github_login: string; count: number }>();
  for (const d of decisions) {
    if (!d.departed) continue;
    const row = byId.get(d.owner_github_id) ?? { github_id: d.owner_github_id, github_login: d.github_login, count: 0 };
    row.count += 1;
    byId.set(d.owner_github_id, row);
  }
  return [...byId.values()];
}

const TRANSFER_WINDOW_DAYS = 7;
const MS_PER_DAY = 86_400_000;

/** 이번 주(최근 7일) 이 팀에서 사람 사이를 건너간 판단 수 — 북극성 지표 (G0) */
export async function weeklyTransferCount(supabase: SupabaseClient, teamId: string, now: Date): Promise<number> {
  const since = new Date(now.getTime() - TRANSFER_WINDOW_DAYS * MS_PER_DAY).toISOString();
  const { data, error } = await supabase.rpc("team_transfer_count", { team: teamId, since });
  if (error) fail("weeklyTransferCount", error);
  return Number(data ?? 0);
}
