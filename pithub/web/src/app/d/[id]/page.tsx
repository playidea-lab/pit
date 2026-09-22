import Link from "next/link";
import { notFound } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import VerifyBar from "@/components/VerifyBar";
import { deleteDecision, setVisibility } from "@/lib/actions";
import { getMyAccount, getMyDecision, getPublicDecision } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

const VISIBILITY_LABEL: Record<string, string> = {
  private: "비공개",
  team: "팀",
  friends: "친구",
  public: "공개",
};

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
  const isPublic = mine?.visibility === "public";

  return (
    <main>
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="page">
        <div className="faint mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {owner && (
            <Link href={`/u/${owner}`} className="muted hover:text-ink">
              {owner}
            </Link>
          )}
          <span>{formatDate(shown.decided_at)}</span>
          {mine && (
            <span className={isPublic ? "text-[var(--approve-fg)]" : ""}>
              {VISIBILITY_LABEL[mine.visibility]} · {mine.status === "confirmed" ? "확인됨" : "미확인"}
            </span>
          )}
        </div>

        <div className="mb-8">
          <VerdictBadge verdict={shown.verdict} chosen={shown.chosen} />
        </div>

        <div className="card space-y-6">
          <Row label="상황">{shown.situation}</Row>
          <Row label="제안">
            <span className="text-[17px] font-medium text-ink">{shown.proposal}</span>
          </Row>
          {shown.options.length > 0 && <Row label="선택지">{shown.options.join(" · ")}</Row>}
          <Row label="내 말">
            <blockquote className="quote">{shown.human_quote}</blockquote>
          </Row>
          {shown.rationale && shown.rationale !== shown.human_quote && <Row label="근거">{shown.rationale}</Row>}
          {shown.supersedes.length > 0 && (
            <Row label="뒤집은 결정">
              {shown.supersedes.map((prev) => (
                <Link key={prev} href={`/d/${prev}`} className="link mr-3 font-mono text-sm">
                  {prev}
                </Link>
              ))}
            </Row>
          )}
          {mine && Object.keys(mine.source).length > 0 && (
            <Row label="출처 · 본인만">
              <span className="muted text-sm">
                {Object.entries(mine.source)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(" · ")}
              </span>
            </Row>
          )}
        </div>

        {mine && mine.status === "draft" && (
          <div className="card mt-6 border-[var(--accent)]/30 bg-[var(--accent-soft)]/40">
            <p className="mb-3 text-sm text-ink">
              AI가 기록했고 아직 확인하지 않은 결정입니다. 공유하려면 먼저 확인해 주세요.
            </p>
            <VerifyBar decision={mine} compact />
          </div>
        )}

        {mine && mine.status === "confirmed" && (
          <div className="mt-6 flex items-center gap-2">
            <form action={setVisibility}>
              <input type="hidden" name="id" value={mine.id} />
              <input type="hidden" name="visibility" value={isPublic ? "private" : "public"} />
              <button className={isPublic ? "btn btn-secondary" : "btn btn-primary"}>
                {isPublic ? "비공개로 전환" : "공개하기"}
              </button>
            </form>
            <form action={deleteDecision} className="ml-auto">
              <input type="hidden" name="id" value={mine.id} />
              <button className="btn btn-danger">삭제</button>
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
      <dt className="label mb-1.5">{label}</dt>
      <dd className="leading-relaxed">{children}</dd>
    </div>
  );
}
