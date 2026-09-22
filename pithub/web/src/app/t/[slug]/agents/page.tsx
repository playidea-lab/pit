import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import Header from "@/components/Header";
import { draftAgentsMd } from "@/lib/agents-md";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { getTeamBySlug, listTeamDecisions } from "@/lib/teams";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ slug: string }>;
}

/** AGENTS.md 초안 — 팀 원장에서 만든 제안. 복사해서 저장소에 커밋하는 것은 사람. */
export default async function TeamAgentsPage({ params }: PageProps) {
  const { slug } = await params;
  const user = await getUser();
  if (!user) redirect(`/?next=/t/${slug}/agents`);
  const supabase = await createServerSupabaseClient();
  const [account, team] = await Promise.all([getMyAccount(supabase), getTeamBySlug(supabase, slug)]);
  if (!team) notFound();
  const decisions = await listTeamDecisions(supabase, team.id);
  const draft = draftAgentsMd(team, decisions);

  return (
    <main>
      <Header signedIn handle={account?.github_login} />
      <section className="page space-y-4">
        <div>
          <Link href={`/t/${slug}`} className="faint text-sm hover:text-ink">
            ← {team.name}
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">AGENTS.md 초안</h1>
          <p className="muted mt-1 text-sm">
            팀에 확정된 결정 {decisions.length}건에서 만들었습니다. 생성이 아니라 제안입니다 — 읽고 고쳐서 저장소에
            커밋하세요. 결정이 쌓이면 초안도 바뀝니다.
          </p>
        </div>
        <pre className="code whitespace-pre-wrap">
          <code>{draft}</code>
        </pre>
      </section>
    </main>
  );
}
