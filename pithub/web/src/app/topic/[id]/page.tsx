import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import { addTopicAlias, mergeTopicInto } from "@/lib/actions";
import { getMyAccount } from "@/lib/decisions";
import { KIND_LABEL, getNode, linksAmong, listNodeDecisions, siblingTopics, type GraphDecision } from "@/lib/graph";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

function Entry({ decision, conflicted }: { decision: GraphDecision; conflicted: boolean }) {
  return (
    <Link href={`/d/${decision.id}`} className="card-link block">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="text-ink">{decision.mine ? "나" : decision.author}</span>
        {decision.departed && <span className="badge badge-modify">떠난 구성원</span>}
        <span className="faint">{formatDate(decision.decided_at)}</span>
        {!decision.verified && <span className="faint">미확인</span>}
        {conflicted && <span className="badge badge-reject ml-auto">충돌 후보</span>}
      </div>
      <p className="muted mb-1 text-sm">{decision.situation}</p>
      <p className="text-[15px] font-medium text-ink">{decision.proposal}</p>
      <blockquote className="quote mt-2 text-sm">{decision.human_quote}</blockquote>
    </Link>
  );
}

/**
 * 주제 화면 — 한 노드에 매달린, 내가 볼 수 있는 모든 사람의 판단 타임라인과 그 사이의 충돌.
 * 기획자의 결정과 개발자의 결정이 같은 주제 아래 나란히 놓이는 곳이다 (D-0009 §6).
 */
export default async function TopicPage({ params }: PageProps) {
  const { id } = await params;
  const user = await getUser();
  if (!user) redirect(`/?next=/topic/${id}`);
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");
  const node = await getNode(supabase, id);
  if (!node) notFound();

  const decisions = await listNodeDecisions(supabase, node.id, account.github_id);
  const links = await linksAmong(supabase, decisions.map((d) => d.id));
  const conflicted = new Set(
    links.filter((l) => l.relation === "conflicts_with").flatMap((l) => [l.from_decision, l.to_decision]),
  );
  const authors = new Set(decisions.map((d) => (d.mine ? account.github_login : d.author)));
  const siblings = await siblingTopics(supabase, node);

  return (
    <main>
      <Header signedIn />
      <section className="page space-y-6">
        <div>
          <p className="label mb-2">{KIND_LABEL[node.kind]}</p>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{node.name}</h1>
          <p className="muted mt-1 text-sm">
            판단 {decisions.length}건 · {authors.size}명
            {conflicted.size > 0 && ` · 충돌 후보 ${conflicted.size}건`}
          </p>
          {node.aliases.length > 0 && <p className="faint mt-1 text-xs">다른 이름: {node.aliases.join(" · ")}</p>}
        </div>

        <details className="card text-sm">
          <summary className="cursor-pointer text-ink">이 주제 다듬기 — 다른 이름 붙이기 · 다른 주제에 합치기</summary>
          <div className="mt-3 space-y-3">
            <form action={addTopicAlias} className="flex flex-wrap gap-2">
              <input type="hidden" name="node_id" value={node.id} />
              <input name="alias" placeholder="같은 뜻의 다른 이름 (예: train/test split)" className="input max-w-xs" />
              <button className="btn btn-secondary shrink-0">다른 이름 추가</button>
            </form>
            {siblings.length > 0 && (
              <form action={mergeTopicInto} className="flex flex-wrap gap-2">
                <input type="hidden" name="node_id" value={node.id} />
                <select name="into" className="input max-w-xs" defaultValue="">
                  <option value="" disabled>
                    합칠 주제 고르기
                  </option>
                  {siblings.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
                <button className="btn btn-secondary shrink-0">이 주제를 거기에 합치기</button>
              </form>
            )}
            <p className="faint text-xs">
              AI가 같은 것을 다른 말로 부를 때 씁니다. 다른 이름을 붙이면 앞으로 그 이름으로 기록된 판단이 이 주제로 모입니다.
            </p>
          </div>
        </details>
        {decisions.length === 0 ? (
          <div className="empty">볼 수 있는 판단이 없습니다.</div>
        ) : (
          <div className="space-y-3">
            {decisions.map((d) => (
              <Entry key={d.id} decision={d} conflicted={conflicted.has(d.id)} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
