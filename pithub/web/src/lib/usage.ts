/**
 * 사용량 — 호출이 얼마나 잦고, 돌려준 결과가 실제로 쓰였는가 (D-0006 A1 · 토큰 비용의 계기판)
 *
 * 서버가 모든 검색을 citations 에 남기고, get_decision 이 결정의 last_cited_at 을 찍는다.
 * "쓰였다" = 검색이 돌려준 결정이 그 검색 이후에 읽혔다. 근사치이고, 본인 결정에 한한다.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

export const USAGE_WINDOW_DAYS = 7;
const MS_PER_DAY = 86_400_000;

export interface UsageSummary {
  days: number;
  searches: number;
  returned: number;
  used: number;
  records: number;
  /** 클라이언트별 (검색 횟수, 기록 건수) */
  byClient: { client: string; searches: number; records: number }[];
}

interface CitationRow {
  returned_ids: string[];
  client: string | null;
  created_at: string;
}

function fail(where: string, error: { message: string } | null): never {
  throw new Error(`${where}: ${error?.message ?? "unknown error"}`);
}

function bump(map: Map<string, { searches: number; records: number }>, client: string, key: "searches" | "records") {
  const row = map.get(client) ?? { searches: 0, records: 0 };
  row[key] += 1;
  map.set(client, row);
}

export async function usageSummary(supabase: SupabaseClient, days = USAGE_WINDOW_DAYS): Promise<UsageSummary> {
  const since = new Date(Date.now() - days * MS_PER_DAY).toISOString();
  const [{ data: citations, error: cErr }, { data: recorded, error: rErr }] = await Promise.all([
    supabase.from("citations").select("returned_ids, client, created_at").gte("created_at", since),
    supabase.from("decisions").select("source").gte("created_at", since).neq("status", "discarded"),
  ]);
  if (cErr) fail("usageSummary.citations", cErr);
  if (rErr) fail("usageSummary.decisions", rErr);

  const searches = (citations ?? []) as CitationRow[];
  const returnedIds = [...new Set(searches.flatMap((s) => s.returned_ids))];
  const citedAt = new Map<string, string>();
  if (returnedIds.length > 0) {
    const { data, error } = await supabase.from("decisions").select("id, last_cited_at").in("id", returnedIds);
    if (error) fail("usageSummary.cited", error);
    for (const row of data ?? []) if (row.last_cited_at) citedAt.set(row.id as string, row.last_cited_at as string);
  }

  const byClient = new Map<string, { searches: number; records: number }>();
  let returned = 0;
  let used = 0;
  for (const s of searches) {
    bump(byClient, s.client ?? "?", "searches");
    returned += s.returned_ids.length;
    used += s.returned_ids.filter((id) => (citedAt.get(id) ?? "") >= s.created_at).length;
  }
  for (const r of recorded ?? []) {
    const source = (r.source ?? {}) as Record<string, string>;
    bump(byClient, source.client ?? "?", "records");
  }

  return {
    days,
    searches: searches.length,
    returned,
    used,
    records: (recorded ?? []).length,
    byClient: [...byClient.entries()].map(([client, v]) => ({ client, ...v })).sort((a, b) => b.records - a.records),
  };
}
