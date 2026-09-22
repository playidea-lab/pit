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
    <main>
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="page">
        <div className="mb-8 flex items-center gap-4">
          {avatar && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatar} alt={handle} className="h-12 w-12 rounded-full border border-border" />
          )}
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">{handle}</h1>
            <p className="muted text-sm">공개한 결정 {decisions.length}건</p>
          </div>
        </div>

        <div className="mb-6 flex items-center gap-1.5">
          {FILTERS.map((f) => (
            <Link
              key={f.value}
              href={{ pathname: `/u/${handle}`, query: f.value ? { verdict: f.value } : {} }}
              className={`tab ${verdict === f.value ? "tab-active" : ""}`}
            >
              {f.label}
            </Link>
          ))}
        </div>

        {decisions.length === 0 ? (
          <div className="empty">공개된 결정이 없습니다.</div>
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
