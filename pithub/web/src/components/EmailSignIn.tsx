"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase";

/** 이메일 로그인 — 매직 링크. 비밀번호는 쓰지 않는다. */
export default function EmailSignIn({ next }: { next: string | null }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    const supabase = createClient();
    if (!supabase || !email.trim()) return;
    setState("sending");
    const callback = new URL("/auth/callback", window.location.origin);
    if (next) callback.searchParams.set("next", next);
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: callback.toString() },
    });
    setState(error ? "error" : "sent");
  };

  if (state === "sent") {
    return (
      <p className="rounded-lg border border-[var(--approve-fg)]/30 bg-[var(--approve-bg)] p-3 text-sm text-[var(--approve-fg)]">
        {email} 로 로그인 링크를 보냈습니다. 메일의 링크를 누르면 이어집니다.
      </p>
    );
  }
  return (
    <form onSubmit={send} className="space-y-2">
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="회사 이메일"
        className="input"
      />
      <button disabled={state === "sending"} className="btn btn-primary w-full justify-center">
        {state === "sending" ? "보내는 중…" : "이메일로 로그인 링크 받기"}
      </button>
      {state === "error" && <p className="text-xs text-[var(--reject-fg)]">보내지 못했습니다. 잠시 뒤 다시 시도하세요.</p>}
    </form>
  );
}
