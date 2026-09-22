"use client";

import { useEffect, useRef, useState } from "react";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import { reviewDecision } from "@/lib/actions";
import type { Decision, Verdict } from "@/lib/decisions";

const VERDICTS: { value: Verdict; label: string }[] = [
  { value: "approve", label: "승인" },
  { value: "modify", label: "수정" },
  { value: "reject", label: "거부" },
];

/**
 * 받은함의 후보 하나. 확정 / 판정만 고쳐 확정 / 편집 / 버림.
 * 검토에 걸린 시간을 재서 보낸다 — 추출 품질 통계의 재료다.
 */
export default function InboxItem({ decision }: { decision: Decision }) {
  const shownAt = useRef<number>(0);
  const [editing, setEditing] = useState(false);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    shownAt.current = performance.now();
  }, [decision.id]);

  const stamp = () => setSeconds((performance.now() - shownAt.current) / 1000);
  const meta = [decision.source.client, decision.source.project].filter(Boolean).join(" · ");

  return (
    <article className="card">
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="faint">{formatDate(decision.decided_at)}</span>
        {meta && <span className="faint">{meta}</span>}
        <span className="faint ml-auto">{decision.origin === "mcp" ? "AI가 기록" : "로컬 추출"}</span>
      </div>

      <form action={reviewDecision} onSubmit={stamp} className="space-y-4">
        <input type="hidden" name="id" value={decision.id} />
        <input type="hidden" name="owner_github_id" value={decision.owner_github_id} />
        <input type="hidden" name="seconds" value={seconds.toFixed(1)} />

        {editing ? (
          <div className="space-y-3">
            <Field name="situation" label="상황" value={decision.situation} />
            <Field name="proposal" label="제안" value={decision.proposal} />
            <Field name="human_quote" label="내 말" value={decision.human_quote} />
            <Field name="rationale" label="근거" value={decision.rationale} />
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <p className="label mb-1">상황</p>
              <p className="muted text-sm leading-relaxed">{decision.situation}</p>
            </div>
            <div>
              <p className="label mb-1">제안</p>
              <p className="text-[15px] leading-relaxed text-ink">{decision.proposal}</p>
            </div>
            {decision.options.length > 0 && (
              <div>
                <p className="label mb-1">선택지</p>
                <p className="muted text-sm">{decision.options.join(" · ")}</p>
              </div>
            )}
            <div>
              <p className="label mb-1">내 말</p>
              <blockquote className="quote">{decision.human_quote}</blockquote>
            </div>
            {decision.rationale && decision.rationale !== decision.human_quote && (
              <div>
                <p className="label mb-1">근거</p>
                <p className="muted text-sm leading-relaxed">{decision.rationale}</p>
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <button name="command" value="confirm" className="btn btn-primary">
            확정
          </button>
          {decision.kind === "verdict" &&
            VERDICTS.filter((v) => v.value !== decision.verdict).map((v) => (
              <button key={v.value} name="verdict" value={v.value} className="btn btn-secondary">
                {v.label}으로 확정
              </button>
            ))}
          <button type="button" onClick={() => setEditing((on) => !on)} className="btn btn-ghost">
            {editing ? "편집 취소" : "편집"}
          </button>
          <button name="command" value="discard" className="btn btn-danger ml-auto">
            버림
          </button>
        </div>
      </form>
    </article>
  );
}

function Field({ name, label, value }: { name: string; label: string; value: string }) {
  return (
    <label className="block">
      <span className="label mb-1 block">{label}</span>
      <textarea name={name} defaultValue={value} rows={2} className="input" />
    </label>
  );
}
