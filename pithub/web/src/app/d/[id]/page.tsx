import Link from "next/link";
import { notFound } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import { deleteDecision, setVisibility } from "@/lib/actions";
import { getMyAccount, getMyDecision, getPublicDecision } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

/**
 * 결정 상세. 소유자에게는 전체 열과 공개·삭제 조작이, 그 밖의 사람에게는 공개 뷰의 열만 보인다.
 * 남의 비공개 결정은 존재 여부도 알려 주지 않는다(404).
 */
export default async function DecisionPage({ params }: PageProps) {
  const { id } = await params;
  const supabase = await createServerSupabaseClient();
  const user = await getUser();
  const account = user ? await getMyAccount(supabase) : null;

  const mine = user ? await getMyDecision(supabase, id) : null;
  const published = mine ? null : await getPublicDecision(supabase, id);
  const shown = mine ?? published;
  if (!shown) notFound();

  const owner = mine ? account?.github_login : published?.github_login;

  return (
    <main className="min-h-screen">
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-2 text-sm text-gray-500">
          {owner && (
            <Link href={`/u/${owner}`} className="hover:text-white">
              {owner}
            </Link>
          )}
          <span>· {formatDate(shown.decided_at)}</span>
          {mine && (
            <span className={mine.visibility === "public" ? "text-green-400" : "text-gray-500"}>
              · {mine.visibility === "public" ? "공개" : "비공개"} · {mine.status}
            </span>
          )}
        </div>

        <div className="mb-6">
          <VerdictBadge verdict={shown.verdict} chosen={shown.chosen} />
        </div>

        <dl className="space-y-5">
          <Row label="상황">{shown.situation}</Row>
          <Row label="제안">{shown.proposal}</Row>
          {shown.options.length > 0 && <Row label="선택지">{shown.options.join(" · ")}</Row>}
          <Row label="내 말">
            <blockquote className="border-l-2 border-gray-700 pl-3 text-gray-300">{shown.human_quote}</blockquote>
          </Row>
          {shown.rationale && <Row label="근거">{shown.rationale}</Row>}
          {shown.supersedes.length > 0 && (
            <Row label="뒤집은 결정">
              {shown.supersedes.map((prev) => (
                <Link key={prev} href={`/d/${prev}`} className="text-blue-400 hover:underline mr-3">
                  {prev}
                </Link>
              ))}
            </Row>
          )}
          {mine && Object.keys(mine.source).length > 0 && (
            <Row label="출처 (본인만)">
              {Object.entries(mine.source)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ")}
            </Row>
          )}
        </dl>

        {mine && mine.status === "confirmed" && (
          <div className="mt-10 flex items-center gap-3 border-t border-gray-800 pt-6">
            <form action={setVisibility}>
              <input type="hidden" name="id" value={mine.id} />
              <input type="hidden" name="visibility" value={mine.visibility === "public" ? "private" : "public"} />
              <button className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm">
                {mine.visibility === "public" ? "비공개로 전환" : "공개하기"}
              </button>
            </form>
            <form action={deleteDecision} className="ml-auto">
              <input type="hidden" name="id" value={mine.id} />
              <button className="px-4 py-2 rounded-lg text-sm text-red-300 hover:bg-red-900/40">삭제</button>
            </form>
          </div>
        )}
      </section>
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500 mb-1">{label}</dt>
      <dd className="text-gray-100">{children}</dd>
    </div>
  );
}
