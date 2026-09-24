"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase";

// 로그인에 필요한 것은 신원뿐이다 (AuthButton 과 같은 범위)
const GITHUB_SCOPES = "read:user";
const SETTINGS_PATH = "/settings";

interface LoginMethodsProps {
  hasGitHub: boolean;
  email: string | null;
  linkFailed: boolean;
}

function callbackUrl(): string {
  const callback = new URL("/auth/callback", window.location.origin);
  callback.searchParams.set("next", SETTINGS_PATH);
  return callback.toString();
}

/**
 * 로그인 방법 잇기 — 한 사람이 GitHub 와 이메일 어느 쪽으로 들어와도 같은 계정(같은 결정·팀·트윈).
 * 이미 다른 pithub 계정에 쓰인 GitHub 는 이을 수 없다(인증 서버가 거절) — 계정 합치기는 하지 않는다.
 */
export default function LoginMethods({ hasGitHub, email, linkFailed }: LoginMethodsProps) {
  const [newEmail, setNewEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "sent" | "error">("idle");

  const linkGitHub = async () => {
    const supabase = createClient();
    if (!supabase) return;
    setState("busy");
    const { error } = await supabase.auth.linkIdentity({
      provider: "github",
      options: { redirectTo: callbackUrl(), scopes: GITHUB_SCOPES },
    });
    if (error) setState("error");
  };

  const addEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    const supabase = createClient();
    if (!supabase || !newEmail.trim()) return;
    setState("busy");
    const { error } = await supabase.auth.updateUser({ email: newEmail.trim() }, { emailRedirectTo: callbackUrl() });
    setState(error ? "error" : "sent");
  };

  return (
    <div className="space-y-3 text-sm">
      <ul className="space-y-1">
        <li className="flex items-center gap-2">
          <span className="text-ink">GitHub</span>
          {hasGitHub ? (
            <span className="badge badge-approve">연결됨</span>
          ) : (
            <button onClick={linkGitHub} disabled={state === "busy"} className="btn btn-secondary ml-auto h-8 px-3">
              GitHub 연결
            </button>
          )}
        </li>
        <li className="flex items-center gap-2">
          <span className="text-ink">이메일 링크</span>
          {email ? <span className="muted">{email}</span> : <span className="faint">없음</span>}
        </li>
      </ul>
      {!email && state !== "sent" && (
        <form onSubmit={addEmail} className="flex gap-2">
          <input
            type="email"
            required
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="이메일로도 로그인하려면"
            className="input max-w-xs"
          />
          <button disabled={state === "busy"} className="btn btn-secondary shrink-0">
            이메일 추가
          </button>
        </form>
      )}
      {state === "sent" && <p className="muted">{newEmail} 로 확인 메일을 보냈습니다. 링크를 누르면 연결됩니다.</p>}
      {(state === "error" || linkFailed) && (
        <p className="text-xs text-[var(--reject-fg)]">
          연결하지 못했습니다. 그 GitHub·이메일이 이미 다른 pithub 계정에 쓰이고 있으면 이을 수 없습니다.
        </p>
      )}
      <p className="faint text-xs">어느 방법으로 들어와도 같은 계정입니다 — 결정·팀·트윈이 그대로 이어집니다.</p>
    </div>
  );
}
