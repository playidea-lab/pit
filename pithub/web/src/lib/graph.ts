/**
 * 판단 그래프 읽기 (G4) — 모두 사용자 세션으로 읽고 RLS가 거른다.
 *
 * 노드·엣지는 부모 결정을 볼 수 있을 때만 보인다. 결정 본문은 내 것이면 decisions 에서,
 * 남의 것이면 team_decisions 뷰(출처·가림 내역 없음)에서 가져온다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import type { SharedDecision } from "@/lib/decisions";

export type NodeKind = "topic" | "project" | "artifact";
export type LinkRelation = "supersedes" | "conflicts_with" | "depends_on";

export interface GraphNode {
  id: string;
  kind: NodeKind;
  name: string;
  team_id: string | null;
}

/** 그래프 화면의 결정 한 줄 — 누구 것인지와 확인 여부가 붙는다 */
export interface GraphDecision extends SharedDecision {
  author: string | null;
  mine: boolean;
  verified: boolean;
  departed: boolean;
}

export interface GraphLink {
  from_decision: string;
  to_decision: string;
  relation: LinkRelation;
  status: "proposed" | "confirmed";
}

const NODE_DECISION_LIMIT = 100;
const SHARED_COLUMNS = "id, kind, verdict, reject_kind, situation, proposal, options, chosen, rationale, human_quote, tags, supersedes, decided_at";

export const KIND_LABEL: Record<NodeKind, string> = { topic: "주제", project: "프로젝트", artifact: "산출물" };
export const RELATION_LABEL: Record<LinkRelation, string> = {
  supersedes: "뒤집음",
  conflicts_with: "충돌",
  depends_on: "전제로 함",
};

function fail(where: string, error: { message: string } | null): never {
  throw new Error(`${where}: ${error?.message ?? "unknown error"}`);
}

export async function getNode(supabase: SupabaseClient, id: string): Promise<(GraphNode & { aliases: string[] }) | null> {
  const { data, error } = await supabase.from("nodes").select("id, kind, name, team_id, aliases").eq("id", id).maybeSingle();
  if (error) fail("getNode", error);
  return (data as (GraphNode & { aliases: string[] }) | null) ?? null;
}

/** 결정 id 들을 본문과 함께 — 내 것과 팀에 보인 남의 것을 합친다 */
export async function loadDecisions(supabase: SupabaseClient, ids: string[], me: number): Promise<GraphDecision[]> {
  if (ids.length === 0) return [];
  const [{ data: mine, error: mineError }, { data: shared, error: sharedError }] = await Promise.all([
    supabase.from("decisions").select(`${SHARED_COLUMNS}, status`).in("id", ids).neq("status", "discarded"),
    supabase.from("team_decisions").select(`${SHARED_COLUMNS}, owner_github_id, github_login, verified, departed`).in("id", ids),
  ]);
  if (mineError) fail("loadDecisions.mine", mineError);
  if (sharedError) fail("loadDecisions.shared", sharedError);
  const byId = new Map<string, GraphDecision>();
  for (const row of shared ?? []) {
    byId.set(row.id, {
      ...(row as unknown as SharedDecision),
      author: row.github_login as string,
      mine: row.owner_github_id === me,
      verified: Boolean(row.verified),
      departed: Boolean(row.departed),
    });
  }
  for (const row of mine ?? []) {
    byId.set(row.id, {
      ...(row as unknown as SharedDecision),
      author: null,
      mine: true,
      verified: row.status === "confirmed",
      departed: false,
    });
  }
  return [...byId.values()].sort((a, b) => b.decided_at.localeCompare(a.decided_at));
}

/** 한 노드에 매달린, 내가 볼 수 있는 모든 결정 */
export async function listNodeDecisions(supabase: SupabaseClient, nodeId: string, me: number): Promise<GraphDecision[]> {
  const { data, error } = await supabase
    .from("decision_nodes")
    .select("decision_id")
    .eq("node_id", nodeId)
    .limit(NODE_DECISION_LIMIT);
  if (error) fail("listNodeDecisions", error);
  return loadDecisions(supabase, (data ?? []).map((r) => r.decision_id as string), me);
}

/** 결정 하나가 매달린 노드들 */
export async function nodesOfDecision(supabase: SupabaseClient, decisionId: string): Promise<GraphNode[]> {
  const { data, error } = await supabase
    .from("decision_nodes")
    .select("nodes(id, kind, name, team_id)")
    .eq("decision_id", decisionId);
  if (error) fail("nodesOfDecision", error);
  return (data ?? []).flatMap((row) => {
    const node = row.nodes as unknown as GraphNode | GraphNode[] | null;
    return Array.isArray(node) ? node : node ? [node] : [];
  });
}

/** 결정들 사이의 링크 — 한쪽이라도 ids 에 있는 것 (RLS가 양 끝을 모두 볼 수 있을 때만 준다) */
export async function linksAmong(supabase: SupabaseClient, ids: string[]): Promise<GraphLink[]> {
  if (ids.length === 0) return [];
  const list = ids.map((id) => `"${id}"`).join(",");
  const { data, error } = await supabase
    .from("decision_links")
    .select("from_decision, to_decision, relation, status")
    .or(`from_decision.in.(${list}),to_decision.in.(${list})`);
  if (error) fail("linksAmong", error);
  return (data ?? []) as GraphLink[];
}

export interface ConflictCandidate {
  id: number;
  a: GraphDecision;
  b: GraphDecision;
}

const CONFLICT_LIST_LIMIT = 30;

/** 처리할 충돌 후보 — 양 끝을 모두 볼 수 있고(RLS), 한쪽이 내 결정인 것 (G5) */
export async function listConflictCandidates(supabase: SupabaseClient, me: number): Promise<ConflictCandidate[]> {
  const { data, error } = await supabase
    .from("decision_links")
    .select("id, from_decision, to_decision")
    .eq("relation", "conflicts_with")
    .eq("status", "proposed")
    .order("created_at", { ascending: false })
    .limit(CONFLICT_LIST_LIMIT);
  if (error) fail("listConflictCandidates", error);
  const rows = (data ?? []) as { id: number; from_decision: string; to_decision: string }[];
  const decisions = new Map(
    (await loadDecisions(supabase, rows.flatMap((r) => [r.from_decision, r.to_decision]), me)).map((d) => [d.id, d]),
  );
  return rows.flatMap((r) => {
    const a = decisions.get(r.from_decision);
    const b = decisions.get(r.to_decision);
    return a && b && (a.mine || b.mine) ? [{ id: r.id, a, b }] : [];
  });
}

export interface MergeCandidate {
  keep_id: string;
  keep_name: string;
  keep_count: number;
  drop_id: string;
  drop_name: string;
  drop_count: number;
  kind: NodeKind;
  similarity: number;
}

const MERGE_LIST_LIMIT = 10;

/** 이름이 비슷한 노드 쌍 — 내가 다룰 수 있는 이름 공간에서만 (G3). 많이 쓰인 쪽이 keep. */
export async function listMergeCandidates(supabase: SupabaseClient): Promise<MergeCandidate[]> {
  const { data, error } = await supabase.rpc("node_merge_candidates", { max_pairs: MERGE_LIST_LIMIT });
  if (error) fail("listMergeCandidates", error);
  return (data ?? []) as MergeCandidate[];
}

export interface TopicSummary extends GraphNode {
  aliases: string[];
  uses: number;
}

const TOPIC_LIST_LIMIT = 200;

/** 내가 볼 수 있는 노드와 매달린 (볼 수 있는) 결정 수 — RLS가 노드와 엣지를 모두 거른다 (그래프 D) */
export async function listTopics(supabase: SupabaseClient, teamId?: string): Promise<TopicSummary[]> {
  let query = supabase
    .from("nodes")
    .select("id, kind, name, team_id, aliases, decision_nodes(count)")
    .is("merged_into", null)
    .limit(TOPIC_LIST_LIMIT);
  if (teamId) query = query.eq("team_id", teamId);
  const { data, error } = await query;
  if (error) fail("listTopics", error);
  return (data ?? [])
    .map((row) => {
      const counted = row.decision_nodes as unknown as { count: number }[] | null;
      return {
        id: row.id as string,
        kind: row.kind as NodeKind,
        name: row.name as string,
        team_id: row.team_id as string | null,
        aliases: (row.aliases as string[] | null) ?? [],
        uses: counted?.[0]?.count ?? 0,
      };
    })
    .filter((t) => t.uses > 0)
    .sort((a, b) => b.uses - a.uses || a.name.localeCompare(b.name));
}

/** 같은 이름 공간·같은 종류의 다른 노드 — "다른 주제에 합치기"의 후보 */
export async function siblingTopics(supabase: SupabaseClient, node: GraphNode & { owner_github_id?: number | null }): Promise<GraphNode[]> {
  let query = supabase.from("nodes").select("id, kind, name, team_id").is("merged_into", null).eq("kind", node.kind).neq("id", node.id);
  query = node.team_id ? query.eq("team_id", node.team_id) : query.is("team_id", null);
  const { data, error } = await query.order("name").limit(TOPIC_LIST_LIMIT);
  if (error) fail("siblingTopics", error);
  return (data ?? []) as GraphNode[];
}
