import Link from "next/link";

import type { PublicDecision, Verdict } from "@/lib/decisions";

const VERDICT_STYLE: Record<Verdict, string> = {
  approve: "bg-green-900/60 text-green-300 border-green-700",
  modify: "bg-yellow-900/60 text-yellow-300 border-yellow-700",
  reject: "bg-red-900/60 text-red-300 border-red-700",
};

const VERDICT_LABEL: Record<Verdict, string> = { approve: "승인", modify: "수정", reject: "거부" };

export function VerdictBadge({ verdict, chosen }: { verdict: Verdict | null; chosen: string | null }) {
  if (verdict) {
    return (
      <span className={`px-2 py-0.5 rounded border text-xs font-medium ${VERDICT_STYLE[verdict]}`}>
        {VERDICT_LABEL[verdict]}
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded border text-xs font-medium bg-blue-900/60 text-blue-300 border-blue-700">
      선택: {chosen}
    </span>
  );
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

type CardDecision = Pick<
  PublicDecision,
  "id" | "verdict" | "chosen" | "situation" | "proposal" | "human_quote" | "decided_at"
>;

/** 타임라인·목록의 한 줄. href를 주면 상세로 이어진다. */
export default function DecisionCard({ decision, href }: { decision: CardDecision; href: string }) {
  return (
    <Link
      href={href}
      className="block rounded-lg border border-gray-800 bg-gray-900/60 p-4 hover:border-gray-600 transition-colors"
    >
      <div className="flex items-center gap-3 mb-2">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="text-xs text-gray-500">{formatDate(decision.decided_at)}</span>
      </div>
      <p className="text-sm text-gray-400 mb-1">{decision.situation}</p>
      <p className="text-gray-100">{decision.proposal}</p>
      {decision.human_quote && (
        <blockquote className="mt-2 border-l-2 border-gray-700 pl-3 text-sm text-gray-300">
          {decision.human_quote}
        </blockquote>
      )}
    </Link>
  );
}
