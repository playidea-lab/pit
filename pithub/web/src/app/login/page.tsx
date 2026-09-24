import { redirect } from "next/navigation";

import { GitHubSignIn } from "@/components/AuthButton";
import EmailSignIn from "@/components/EmailSignIn";
import Header from "@/components/Header";
import { getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

// 같은 사이트의 경로만 돌아갈 곳으로 받는다 (auth/callback 의 SAFE_NEXT 와 같은 규칙)
const SAFE_NEXT = /^\/(?![/\\])[A-Za-z0-9_\-/.~]*(\?[A-Za-z0-9_\-=&%.~]*)?$/;

interface PageProps {
  searchParams: Promise<{ next?: string; error?: string }>;
}

/** 로그인 — GitHub 또는 이메일(매직 링크). 둘 다 같은 pithub 계정 체계로 들어간다. */
export default async function LoginPage({ searchParams }: PageProps) {
  const { next: requested, error } = await searchParams;
  const next = requested && SAFE_NEXT.test(requested) ? requested : null;
  if (await getUser()) redirect(next ?? "/");

  return (
    <main>
      <Header signedIn={false} />
      <section className="page">
        <div className="card mx-auto max-w-sm space-y-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-ink">pithub 로그인</h1>
            <p className="muted mt-1 text-sm">회사 이메일이나 GitHub 계정으로 들어옵니다.</p>
          </div>
          {error && (
            <p className="rounded-lg border border-[var(--reject-fg)]/30 p-3 text-sm text-[var(--reject-fg)]">
              로그인 링크를 열지 못했습니다. 요청한 브라우저와 다른 곳에서 열었거나 만료된 링크입니다. 이메일을 다시 넣고
              메일의 코드를 입력하세요.
            </p>
          )}
          <EmailSignIn next={next} />
          <div className="faint flex items-center gap-3 text-xs">
            <span className="h-px flex-1 bg-[var(--border)]" />
            또는
            <span className="h-px flex-1 bg-[var(--border)]" />
          </div>
          <GitHubSignIn next={next} />
        </div>
      </section>
    </main>
  );
}
