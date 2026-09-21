import Link from "next/link";

import DecisionCard from "@/components/DecisionCard";
import Header from "@/components/Header";
import { getMyAccount, listPublicDecisions, type Verdict } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

const FILTERS: { value: Verdict | ""; label: string }[] = [
  { value: "", label: "전체" },
  { value: "approve", label: "승인" },
  { value: "modify", label: "수정" },
  { value: "reject", label: "거부" },
];

interface PageProps {
  params: Promise<{ handle: string }>;
  searchParams: Promise<{ verdict?: string }>;
}

/** 공개 타임라인 — 로그인 없이 볼 수 있다. public_decisions 뷰만 읽는다. */
export default async function PublicProfilePage({ params, searchParams }: PageProps) {
  const { handle } = await params;
  const { verdict = "" } = await searchParams;
  const supabase = await createServerSupabaseClient();
  const user = await getUser();
  const [account, decisions] = await Promise.all([
    user ? getMyAccount(supabase) : null,
    listPublicDecisions(supabase, handle, (verdict || undefined) as Verdict | undefined),
  ]);
  const avatar = decisions[0]?.avatar_url;

  return (
    <main className="min-h-screen">
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-6">
          {avatar && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatar} alt={handle} className="w-10 h-10 rounded-full" />
          )}
          <h1 className="text-2xl font-bold">{handle}</h1>
          <span className="text-sm text-gray-500">공개한 결정</span>
        </div>

        <div className="flex items-center gap-2 mb-6">
          {FILTERS.map((f) => (
            <Link
              key={f.value}
              href={{ pathname: `/u/${handle}`, query: f.value ? { verdict: f.value } : {} }}
              className={`px-3 py-1.5 rounded-lg text-sm ${
                verdict === f.value ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"
              }`}
            >
              {f.label}
            </Link>
          ))}
        </div>

        {decisions.length === 0 ? (
          <p className="text-gray-400">공개된 결정이 없습니다.</p>
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
