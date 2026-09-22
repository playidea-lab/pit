/**
 * AGENTS.md 초안 — 팀에 확정된 결정에서 만든다.
 *
 * 생성이 아니라 제안이다. 사람이 읽고 고쳐서 저장소에 커밋한다.
 * 원칙 → 하지 않기로 한 것 → 고른 것 순서. 많이 쓰인 것(인용 횟수)이 위로 온다.
 */

import type { TeamDecision } from "@/lib/teams";

const MAX_PER_SECTION = 20;
const QUOTE_CHARS = 120;

function byUsage(a: TeamDecision, b: TeamDecision): number {
  return b.cited_count - a.cited_count || b.decided_at.localeCompare(a.decided_at);
}

function quote(decision: TeamDecision): string {
  const words = decision.human_quote.replace(/\s+/g, " ").trim();
  return words.length > QUOTE_CHARS ? `${words.slice(0, QUOTE_CHARS)}…` : words;
}

function attribution(decision: TeamDecision): string {
  return `${decision.github_login}, ${decision.decided_at.slice(0, 10)}`;
}

function section(title: string, lines: string[]): string[] {
  return lines.length === 0 ? [] : [`## ${title}`, "", ...lines, ""];
}

export function draftAgentsMd(team: { name: string; slug: string }, decisions: TeamDecision[], now = new Date()): string {
  const sorted = [...decisions].sort(byUsage);
  const principles = sorted.filter((d) => d.tags.includes("principle")).slice(0, MAX_PER_SECTION);
  const principleIds = new Set(principles.map((d) => d.id));
  const rejected = sorted
    .filter((d) => d.verdict === "reject" && !principleIds.has(d.id))
    .slice(0, MAX_PER_SECTION);
  const chosen = sorted.filter((d) => d.kind === "choice" && d.chosen && !principleIds.has(d.id)).slice(0, MAX_PER_SECTION);

  const header = [
    `# AGENTS.md — ${team.name}`,
    "",
    `> pithub 팀 원장(${team.slug})의 확정된 결정 ${decisions.length}건에서 만든 초안, ${now.toISOString().slice(0, 10)}.`,
    "> 사람이 검토해 커밋한다. 항목 뒤의 괄호는 결정한 사람과 날짜.",
    "",
  ];
  return [
    ...header,
    ...section(
      "원칙",
      principles.map((d) => `- ${d.proposal}${d.rationale ? ` — ${d.rationale}` : ""} (${attribution(d)})`),
    ),
    ...section(
      "하지 않기로 한 것",
      rejected.map((d) => `- ${d.proposal} — "${quote(d)}" (${attribution(d)})`),
    ),
    ...section(
      "고른 것",
      chosen.map((d) => `- ${d.proposal}: **${d.chosen}** (${attribution(d)})`),
    ),
  ].join("\n");
}
