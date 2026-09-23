import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import VerifyBar from "@/components/VerifyBar";
import { deleteDecision, withdrawFromTeam } from "@/lib/actions";
import { getMyAccount, getMyDecision, isTeamShared, teamShareAt } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { getTeamDecision } from "@/lib/teams";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

// 요청 시점의 시각 — react-hooks/purity 가 컴포넌트 본문의 Date 생성을 막으므로 밖에서 읽는다
function requestTime(): Date {
  return new Date();
}

/**
 * 결정 상세. 작성자에게는 전체 열과 조작이, 팀원에게는 팀 뷰의 열만 보인다.
 * 남의 비공개 결정은 존재 여부도 알려 주지 않는다(404). 회사 밖으로 나가는 경로는 없다 (D-0010).
 */
export default async function DecisionPage({ params }: PageProps) {
  const { id } = await params;
  const user = await getUser();
  if (!user) redirect(`/?next=/d/${id}`);
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);

  const mine = await getMyDecision(supabase, id);
  const teamShown = mine ? null : await getTeamDecision(supabase, id);
  const shown = mine ?? teamShown;
  if (!shown) notFound();

  const now = requestTime();
  const shared = mine ? isTeamShared(mine, now) : true;
  const shareAt = mine ? teamShareAt(mine) : null;
  const owner = mine ? account?.github_login : teamShown?.github_login;

  return (
    <main>
      <Header signedIn />
      <section className="page">
        <div className="faint mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {owner && <span className="muted">{owner}</span>}
          {teamShown?.departed && <span className="badge badge-modify">떠난 구성원</span>}
          <span>{formatDate(shown.decided_at)}</span>
          {mine && <span>{scopeLabel(mine.visibility, mine.status, shared, shareAt)}</span>}
          {teamShown && (
            <Link href={`/t/${teamShown.team_slug}`} className="muted hover:text-ink">
              팀 · {teamShown.team_slug}
              {!teamShown.verified && " · 미확인"}
            </Link>
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
          <Row label={mine ? "내 말" : "그 사람의 말"}>
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
              AI가 기록했고 아직 확인하지 않은 결정입니다.
              {mine.visibility === "team" && !shared && " 맞으면 확인하고, 팀에 보이면 안 되면 빼 주세요."}
            </p>
            <VerifyBar decision={mine} compact />
          </div>
        )}

        {mine && (
          <div className="mt-6 flex items-center gap-2">
            {mine.visibility === "team" && !shared && (
              <form action={withdrawFromTeam}>
                <input type="hidden" name="id" value={mine.id} />
                <button className="btn btn-secondary">팀에서 빼기</button>
              </form>
            )}
            {shared ? (
              <p className="faint text-xs">
                팀에 보인 결정은 회사의 기록입니다. 지우려면 팀 소유자에게 요청하세요.
              </p>
            ) : (
              <form action={deleteDecision} className="ml-auto">
                <input type="hidden" name="id" value={mine.id} />
                <button className="btn btn-danger">삭제</button>
              </form>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

function scopeLabel(visibility: string, status: string, shared: boolean, shareAt: Date | null): string {
  const verified = status === "confirmed" ? "확인됨" : "미확인";
  if (visibility !== "team") return `본인만 · ${verified}`;
  if (shared) return `팀에 보임 · ${verified}`;
  return `${shareAt ? shareAt.toLocaleDateString("ko-KR") : "3일 뒤"} 팀에 보임 · ${verified}`;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label mb-1.5">{label}</dt>
      <dd className="leading-relaxed">{children}</dd>
    </div>
  );
}
