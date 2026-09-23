import { redirect } from "next/navigation";

import AuthButton from "@/components/AuthButton";
import Header from "@/components/Header";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ token: string }>;
}

/**
 * 초대 링크 — 로그인하면 승인 없이 바로 팀원이 되고 연결 안내로 간다.
 * 로그인 전에는 무엇을 하는 페이지인지만 알려 준다(팀 이름도 로그인 뒤에야 보인다).
 */
export default async function JoinPage({ params }: PageProps) {
  const { token } = await params;
  const user = await getUser();

  if (user) {
    const supabase = await createServerSupabaseClient();
    const { data, error } = await supabase.rpc("join_team_with_invite", { token });
    if (!error && data) redirect(`/connect?joined=${encodeURIComponent(String(data))}`);
    return (
      <main>
        <Header signedIn />
        <section className="page">
          <div className="empty">
            <p className="mb-2 text-ink">이 초대 링크는 만료되었거나 더 이상 쓸 수 없습니다.</p>
            <p className="text-sm">팀 관리자에게 새 링크를 받아 주세요.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main>
      <Header signedIn={false} />
      <section className="page space-y-6 pt-12">
        <div>
          <p className="label mb-3">pithub 팀 초대</p>
          <h1 className="mb-3 text-3xl font-semibold tracking-tight text-ink">팀에 초대받았습니다</h1>
          <p className="muted max-w-xl leading-relaxed">
            GitHub로 로그인하면 바로 팀에 들어갑니다. 그다음 쓰는 AI 도구(Claude Code · claude.ai · Codex)에 주소 하나를
            붙이면 끝입니다. 평소처럼 일하면, AI의 제안을 거부하거나 방향을 정한 순간이 팀의 판단으로 쌓입니다.
          </p>
        </div>
        <AuthButton />
      </section>
    </main>
  );
}
