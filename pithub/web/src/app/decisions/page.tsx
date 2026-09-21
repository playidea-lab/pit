import Link from "next/link";
import { redirect } from "next/navigation";

import DecisionCard from "@/components/DecisionCard";
import Header from "@/components/Header";
import { getMyAccount, listMyDecisions, type Verdict } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

const FILTERS: { value: Verdict | ""; label: string }[] = [
  { value: "", label: "전체" },
  { value: "approve", label: "승인" },
  { value: "modify", label: "수정" },
  { value: "reject", label: "거부" },
];

interface PageProps {
  searchParams: Promise<{ verdict?: string; q?: string }>;
}

/** 내가 확정한 결정 — 프로젝트와 도구를 가로질러 사람 축으로 */
export default async function MyDecisionsPage({ searchParams }: PageProps) {
  const user = await getUser();
  if (!user) redirect("/?next=/decisions");

  const { verdict = "", q = "" } = await searchParams;
  const supabase = await createServerSupabaseClient();
  const filter = { verdict: (verdict || undefined) as Verdict | undefined, text: q || undefined };
  const [account, decisions] = await Promise.all([getMyAccount(supabase), listMyDecisions(supabase, filter)]);

  return (
    <main className="min-h-screen">
      <Header signedIn handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-10">
        <h1 className="text-2xl font-bold mb-6">내 결정</h1>

        <div className="flex flex-wrap items-center gap-2 mb-6">
          {FILTERS.map((f) => (
            <Link
              key={f.value}
              href={{ pathname: "/decisions", query: { ...(f.value && { verdict: f.value }), ...(q && { q }) } }}
              className={`px-3 py-1.5 rounded-lg text-sm ${
                verdict === f.value ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {f.label}
            </Link>
          ))}
          <form className="ml-auto">
            {verdict && <input type="hidden" name="verdict" value={verdict} />}
            <input
              name="q"
              defaultValue={q}
              placeholder="상황·제안·근거·내 말에서 찾기"
              className="rounded-lg bg-gray-900 border border-gray-700 px-3 py-1.5 text-sm w-64"
            />
          </form>
        </div>

        {decisions.length === 0 ? (
          <p className="text-gray-400">확정한 결정이 없습니다.</p>
        ) : (
          <div className="space-y-3">
            {decisions.map((decision) => (
              <DecisionCard key={decision.id} decision={decision} href={`/d/${decision.id}`} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
