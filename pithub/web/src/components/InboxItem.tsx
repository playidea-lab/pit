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

  return (
    <article className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
      <div className="flex items-center gap-3 mb-3 text-xs text-gray-500">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span>{formatDate(decision.decided_at)}</span>
        {decision.source.client && <span>· {decision.source.client}</span>}
        {decision.source.project && <span>· {decision.source.project}</span>}
        <span className="ml-auto">{decision.origin === "mcp" ? "AI가 기록" : "로컬 추출"}</span>
      </div>

      <form action={reviewDecision} onSubmit={stamp} className="space-y-3">
        <input type="hidden" name="id" value={decision.id} />
        <input type="hidden" name="owner_github_id" value={decision.owner_github_id} />
        <input type="hidden" name="seconds" value={seconds.toFixed(1)} />

        {editing ? (
          <>
            <Field name="situation" label="상황" value={decision.situation} />
            <Field name="proposal" label="제안" value={decision.proposal} />
            <Field name="human_quote" label="내 말" value={decision.human_quote} />
            <Field name="rationale" label="근거" value={decision.rationale} />
          </>
        ) : (
          <>
            <p className="text-sm text-gray-400">{decision.situation}</p>
            <p className="text-gray-100">{decision.proposal}</p>
            {decision.options.length > 0 && (
              <p className="text-sm text-gray-400">선택지: {decision.options.join(" · ")}</p>
            )}
            <blockquote className="border-l-2 border-gray-700 pl-3 text-sm text-gray-300">
              {decision.human_quote}
            </blockquote>
            {decision.rationale && <p className="text-sm text-gray-400">근거: {decision.rationale}</p>}
          </>
        )}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <button name="command" value="confirm" className="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-sm">
            확정
          </button>
          {decision.kind === "verdict" &&
            VERDICTS.filter((v) => v.value !== decision.verdict).map((v) => (
              <button
                key={v.value}
                name="verdict"
                value={v.value}
                className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-sm"
              >
                {v.label}으로 확정
              </button>
            ))}
          <button
            type="button"
            onClick={() => setEditing((on) => !on)}
            className="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-sm"
          >
            {editing ? "편집 취소" : "편집"}
          </button>
          <button
            name="command"
            value="discard"
            className="ml-auto px-3 py-1.5 rounded text-sm text-red-300 hover:bg-red-900/40"
          >
            버림
          </button>
        </div>
      </form>
    </article>
  );
}

function Field({ name, label, value }: { name: string; label: string; value: string }) {
  return (
    <label className="block text-sm">
      <span className="text-gray-400">{label}</span>
      <textarea
        name={name}
        defaultValue={value}
        rows={2}
        className="mt-1 w-full rounded bg-gray-950 border border-gray-700 p-2 text-gray-100"
      />
    </label>
  );
}
