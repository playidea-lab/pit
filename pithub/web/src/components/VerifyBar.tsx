"use client";

import { useEffect, useRef, useState } from "react";

import { reviewDecision } from "@/lib/actions";
import type { Decision, Verdict } from "@/lib/decisions";

const VERDICTS: { value: Verdict; label: string }[] = [
  { value: "approve", label: "승인" },
  { value: "modify", label: "수정" },
  { value: "reject", label: "거부" },
];

/**
 * "쓰는 순간의 확인" — 상세 페이지·정리함·표본 어디서든 같은 한 줄.
 * 맞음 / 판정 고쳐 확인 / 버림. 걸린 시간을 재서 보낸다.
 */
export default function VerifyBar({ decision, compact = false }: { decision: Decision; compact?: boolean }) {
  const shownAt = useRef<number>(0);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    shownAt.current = performance.now();
  }, [decision.id]);

  const stamp = () => setSeconds((performance.now() - shownAt.current) / 1000);

  return (
    <form action={reviewDecision} onSubmit={stamp} className="flex flex-wrap items-center gap-2">
      <input type="hidden" name="id" value={decision.id} />
      <input type="hidden" name="owner_github_id" value={decision.owner_github_id} />
      <input type="hidden" name="seconds" value={seconds.toFixed(1)} />
      {!compact && <span className="faint mr-1 text-xs">이 기록이 맞습니까?</span>}
      <button name="command" value="confirm" className="btn btn-primary h-8 px-3">
        맞음
      </button>
      {decision.kind === "verdict" &&
        VERDICTS.filter((v) => v.value !== decision.verdict).map((v) => (
          <button key={v.value} name="verdict" value={v.value} className="btn btn-secondary h-8 px-3">
            {v.label}이 맞음
          </button>
        ))}
      <button name="command" value="discard" className="btn btn-danger ml-auto h-8 px-3">
        버림
      </button>
    </form>
  );
}
