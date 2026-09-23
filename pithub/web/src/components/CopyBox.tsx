"use client";

import { useState } from "react";

const COPIED_MS = 1500;

/** 복사할 값 한 줄 — 주소·명령·초대 링크. 누르면 클립보드로. */
export default function CopyBox({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), COPIED_MS);
  };

  return (
    <div className="code flex items-center gap-3">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap">{value}</code>
      <button type="button" onClick={copy} className="btn btn-secondary h-7 shrink-0 px-2.5 text-xs">
        {copied ? "복사됨" : (label ?? "복사")}
      </button>
    </div>
  );
}
