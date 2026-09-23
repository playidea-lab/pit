import Link from "next/link";
import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { KIND_LABEL, listTopics, type TopicSummary } from "@/lib/graph";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function TopicList({ title, topics }: { title: string; topics: TopicSummary[] }) {
  if (topics.length === 0) return null;
  return (
    <div>
      <h2 className="mb-3 text-[15px] font-semibold text-ink">{title}</h2>
      <ul className="card divide-y divide-border">
        {topics.map((t) => (
          <li key={t.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="faint w-14 shrink-0 text-xs">{KIND_LABEL[t.kind]}</span>
            <Link href={`/topic/${t.id}`} className="link min-w-0 flex-1 truncate">
              {t.name}
            </Link>
            {t.aliases.length > 0 && <span className="faint truncate text-xs">= {t.aliases.join(", ")}</span>}
            <span className="faint shrink-0 text-xs">판단 {t.uses}건</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * 주제 — 판단 그래프의 입구. 내가 볼 수 있는 결정이 매달린 주제·프로젝트·산출물을 많이 쓰인 순으로.
 * 팀 주제와 내 개인 주제를 나눠 보여 준다 (그래프 D).
 */
export default async function TopicsPage() {
  const user = await getUser();
  if (!user) redirect("/login?next=/topics");
  const supabase = await createServerSupabaseClient();
  const topics = await listTopics(supabase);
  const team = topics.filter((t) => t.team_id);
  const mine = topics.filter((t) => !t.team_id);

  return (
    <main>
      <Header signedIn />
      <section className="page space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">주제</h1>
          <p className="muted mt-1 text-sm">
            판단이 매달린 주제입니다. 누르면 그 주제에 대해 누가 무엇을 정했는지, 서로 충돌하는지 한 화면에 보입니다.
          </p>
        </div>
        {topics.length === 0 && (
          <div className="empty">아직 주제가 없습니다. AI가 판단을 기록할 때 무엇에 관한 것인지 함께 붙입니다.</div>
        )}
        <TopicList title="팀" topics={team} />
        <TopicList title="나만 보는" topics={mine} />
      </section>
    </main>
  );
}
