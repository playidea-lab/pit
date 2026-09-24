"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase";

// 인증 서버의 일회용 코드 길이 (Supabase 기본 6자리, 설정에 따라 최대 10자리)
const OTP_PATTERN = "[0-9]{6,10}";
const DEFAULT_NEXT = "/inbox";

/**
 * 이메일 로그인 — 메일로 온 코드 입력 또는 링크. 비밀번호는 쓰지 않는다.
 * 링크는 요청한 브라우저에서만 열린다(PKCE). 폰의 메신저 안에서 요청하고 PC 메일에서 여는 경우가 흔해서
 * 어느 기기에서 봐도 되는 코드를 먼저 안내한다.
 */
export default function EmailSignIn({ next }: { next: string | null }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "verifying" | "error" | "bad-code">("idle");

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

  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    const supabase = createClient();
    if (!supabase) return;
    setState("verifying");
    const { error } = await supabase.auth.verifyOtp({ email: email.trim(), token: code.trim(), type: "email" });
    if (error) {
      setState("bad-code");
      return;
    }
    // 링크 콜백과 같은 일: 계정을 보장한다 (지웠다가 돌아온 사람 포함)
    const { error: accountError } = await supabase.rpc("ensure_my_account");
    if (accountError) {
      setState("error");
      return;
    }
    window.location.assign(next ?? DEFAULT_NEXT);
  };

  if (state === "sent" || state === "verifying" || state === "bad-code") {
    return (
      <form onSubmit={verify} className="space-y-2">
        <p className="rounded-lg border border-[var(--approve-fg)]/30 bg-[var(--approve-bg)] p-3 text-sm text-[var(--approve-fg)]">
          {email} 로 메일을 보냈습니다. 메일의 <b>코드</b>를 아래에 넣으세요. 링크를 눌러도 되지만, 링크는 이 브라우저에서
          열어야 합니다.
        </p>
        <input
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern={OTP_PATTERN}
          required
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          placeholder="메일로 온 코드"
          className="input text-center tracking-[0.3em]"
        />
        <button disabled={state === "verifying"} className="btn btn-primary w-full justify-center">
          {state === "verifying" ? "확인 중…" : "로그인"}
        </button>
        {state === "bad-code" && (
          <p className="text-xs text-[var(--reject-fg)]">코드가 맞지 않거나 만료됐습니다. 가장 최근 메일의 코드인지 확인하세요.</p>
        )}
        <button type="button" onClick={() => setState("idle")} className="faint w-full text-xs hover:text-ink">
          다른 이메일로 · 다시 보내기
        </button>
      </form>
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
        {state === "sending" ? "보내는 중…" : "이메일로 로그인 코드 받기"}
      </button>
      {state === "error" && <p className="text-xs text-[var(--reject-fg)]">보내지 못했습니다. 잠시 뒤 다시 시도하세요.</p>}
    </form>
  );
}
