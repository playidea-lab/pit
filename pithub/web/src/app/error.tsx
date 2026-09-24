"use client";

import Link from "next/link";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * 화면을 그리다 실패했을 때. 오류 본문에는 저장된 글이 섞일 수 있어 보여 주지 않고,
 * 서버 로그와 맞춰 볼 수 있는 digest 만 보여 준다.
 */
export default function ErrorPage({ error, reset }: ErrorProps) {
  return (
    <main>
      <section className="page space-y-4">
        <Link href="/" className="text-[17px] font-semibold tracking-tight text-ink">
          <span className="text-accent">pit</span>hub
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">문제가 생겼습니다</h1>
        <p className="muted text-sm">
          잠시 뒤 다시 시도해 주세요. 계속되면 아래 번호를 관리자에게 알려 주세요 — 원인을 찾는 데 씁니다.
        </p>
        {error.digest && <p className="faint font-mono text-xs">오류 번호 {error.digest}</p>}
        <div className="flex gap-2">
          <button onClick={reset} className="btn btn-primary">
            다시 시도
          </button>
          <Link href="/" className="btn btn-secondary">
            처음으로
          </Link>
        </div>
      </section>
    </main>
  );
}
