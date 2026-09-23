import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { decideConsent } from "@/lib/consent-actions";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ authorization_id?: string }>;
}

/**
 * AI 도구 연결 동의 — claude.ai·Claude Code·Codex가 pithub에 붙으려 할 때 Supabase Auth(OAuth 2.1 서버)가
 * 이 화면으로 보낸다. 로그인(GitHub·이메일)이 먼저이고, 허용하면 도구로 돌아간다.
 */
export default async function ConsentPage({ searchParams }: PageProps) {
  const { authorization_id: authorizationId } = await searchParams;
  if (!authorizationId) redirect("/");
  if (!(await getUser())) redirect(`/login?next=${encodeURIComponent(`/oauth/consent?authorization_id=${authorizationId}`)}`);

  const supabase = await createServerSupabaseClient();
  const { data, error } = await supabase.auth.oauth.getAuthorizationDetails(authorizationId);
  if (error || !data) {
    return (
      <main>
        <Header signedIn />
        <section className="page">
          <div className="empty">이 연결 요청은 만료되었거나 찾을 수 없습니다. 도구에서 다시 연결해 주세요.</div>
        </section>
      </main>
    );
  }
  // 이미 허용한 도구면 곧바로 돌려보낸다
  if (data.redirect_url) redirect(data.redirect_url);
  const account = await getMyAccount(supabase);
  const clientName = data.client?.name || "AI 도구";

  return (
    <main>
      <Header signedIn />
      <section className="page">
        <form action={decideConsent} className="card mx-auto max-w-md space-y-4">
          <input type="hidden" name="authorization_id" value={authorizationId} />
          <div>
            <p className="label mb-2">연결 요청</p>
            <h1 className="text-xl font-semibold tracking-tight text-ink">{clientName}을(를) pithub에 연결할까요?</h1>
          </div>
          <p className="muted text-sm leading-relaxed">
            <b className="text-ink">{account?.github_login ?? data.user.email}</b> 계정으로 연결됩니다. 연결하면 이 도구의
            AI가 당신이 AI와 일하며 내린 판단을 기록하고, 팀의 판단을 찾아볼 수 있습니다. 대화 원문은 보내지 않습니다.
          </p>
          <div className="flex gap-2">
            <button name="decision" value="approve" className="btn btn-primary">
              연결 허용
            </button>
            <button name="decision" value="deny" className="btn btn-ghost">
              거절
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
