import Link from "next/link";

import type { PublicDecision, Verdict } from "@/lib/decisions";

const VERDICT_LABEL: Record<Verdict, string> = { approve: "승인", modify: "수정", reject: "거부" };

export function VerdictBadge({ verdict, chosen }: { verdict: Verdict | null; chosen: string | null }) {
  if (verdict) {
    return <span className={`badge badge-${verdict}`}>{VERDICT_LABEL[verdict]}</span>;
  }
  return <span className="badge badge-choice">선택 · {chosen}</span>;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

type CardDecision = Pick<
  PublicDecision,
  "id" | "verdict" | "chosen" | "situation" | "proposal" | "human_quote" | "decided_at"
>;

/** 타임라인·목록의 한 줄. href를 주면 상세로 이어진다. */
export default function DecisionCard({
  decision,
  href,
  unverified = false,
}: {
  decision: CardDecision;
  href: string;
  unverified?: boolean;
}) {
  return (
    <Link href={href} className="card-link">
      <div className="mb-3 flex items-center gap-3">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="faint text-xs">{formatDate(decision.decided_at)}</span>
        {unverified && <span className="faint ml-auto text-xs">미확인</span>}
      </div>
      <p className="muted mb-1 text-sm">{decision.situation}</p>
      <p className="text-[15px] font-medium text-ink">{decision.proposal}</p>
      {decision.human_quote && <blockquote className="quote mt-3 text-sm">{decision.human_quote}</blockquote>}
    </Link>
  );
}
