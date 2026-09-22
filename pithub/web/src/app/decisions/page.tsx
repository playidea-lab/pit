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
  searchParams: Promise<{ verdict?: string; q?: string; unverified?: string }>;
}

/** 내 결정 — 확인 여부와 무관하게 기록 전부. 프로젝트와 도구를 가로질러 사람 축으로. */
export default async function MyDecisionsPage({ searchParams }: PageProps) {
  const user = await getUser();
  if (!user) redirect("/?next=/decisions");

  const { verdict = "", q = "", unverified = "" } = await searchParams;
  const supabase = await createServerSupabaseClient();
  const filter = {
    verdict: (verdict || undefined) as Verdict | undefined,
    text: q || undefined,
    unverifiedOnly: unverified === "1",
  };
  const [account, decisions] = await Promise.all([getMyAccount(supabase), listMyDecisions(supabase, filter)]);
  const query = { ...(q && { q }), ...(unverified && { unverified }) };

  return (
    <main>
      <Header signedIn handle={account?.github_login} />
      <section className="page">
        <h1 className="mb-6 text-2xl font-semibold tracking-tight text-ink">내 결정</h1>

        <div className="mb-6 flex flex-wrap items-center gap-1.5">
          {FILTERS.map((f) => (
            <Link
              key={f.value}
              href={{ pathname: "/decisions", query: { ...query, ...(f.value && { verdict: f.value }) } }}
              className={`tab ${verdict === f.value ? "tab-active" : ""}`}
            >
              {f.label}
            </Link>
          ))}
          <Link
            href={{ pathname: "/decisions", query: { ...(q && { q }), ...(verdict && { verdict }), ...(unverified ? {} : { unverified: "1" }) } }}
            className={`tab ${unverified ? "tab-active" : ""}`}
          >
            미확인만
          </Link>
          <form className="ml-auto w-64">
            {verdict && <input type="hidden" name="verdict" value={verdict} />}
            {unverified && <input type="hidden" name="unverified" value={unverified} />}
            <input name="q" defaultValue={q} placeholder="상황·제안·근거·내 말에서 찾기" className="input" />
          </form>
        </div>

        {decisions.length === 0 ? (
          <div className="empty">기록이 없습니다.</div>
        ) : (
          <div className="space-y-3">
            {decisions.map((decision) => (
              <DecisionCard
                key={decision.id}
                decision={decision}
                href={`/d/${decision.id}`}
                unverified={decision.status === "draft"}
              />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
