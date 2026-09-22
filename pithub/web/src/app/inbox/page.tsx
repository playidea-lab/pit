import Link from "next/link";
import { redirect } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import VerifyBar from "@/components/VerifyBar";
import { getMyAccount, leaksVerdict, listUnverified, needsAttention, weeklySample, type Decision } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function Item({ decision }: { decision: Decision }) {
  const redacted = Object.values(decision.redactions).reduce((a, b) => a + b, 0);
  return (
    <article className="card">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="faint">{formatDate(decision.decided_at)}</span>
        {decision.source.project && <span className="faint">{decision.source.project}</span>}
        {decision.visibility === "team" && <span className="badge badge-choice">팀 · 확인하면 팀에 보임</span>}
        {redacted > 0 && <span className="badge badge-modify">가림 {redacted}곳</span>}
        {decision.tags.includes("principle") && <span className="badge badge-choice">원칙</span>}
        {decision.supersedes.length > 0 && <span className="badge badge-choice">이전 결정을 뒤집음</span>}
        {leaksVerdict(decision) && <span className="badge badge-modify">설명에 판정이 섞임</span>}
        <Link href={`/d/${decision.id}`} className="faint ml-auto hover:text-ink">
          자세히
        </Link>
      </div>
      <p className="muted mb-1 text-sm">{decision.situation}</p>
      <p className="mb-2 text-[15px] text-ink">{decision.proposal}</p>
      <blockquote className="quote mb-4 text-sm">{decision.human_quote}</blockquote>
      <VerifyBar decision={decision} compact />
    </article>
  );
}

/**
 * 정리함 — 기록은 자동으로 쌓이고 검색에 바로 쓰인다. 여기에는 사람이 봐 둘 만한 것만 온다:
 * 이번 주 표본 5건(품질 측정), 거부·수정 판정, 가림이 일어난 것. 나머지 승인 기록은 손댈 일이 없다.
 */
export default async function TriagePage() {
  const user = await getUser();
  if (!user) redirect("/?next=/inbox");

  const supabase = await createServerSupabaseClient();
  const [account, unverified] = await Promise.all([getMyAccount(supabase), listUnverified(supabase)]);
  const sample = weeklySample(unverified);
  const sampleIds = new Set(sample.map((d) => d.id));
  const flagged = unverified.filter((d) => needsAttention(d) && !sampleIds.has(d.id));
  const rest = unverified.length - sample.length - flagged.length;

  return (
    <main>
      <Header signedIn handle={account?.github_login} />
      <section className="page space-y-10">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">정리함</h1>
          <p className="muted mt-1 text-sm">
            기록은 자동으로 쌓이고 검색에 바로 쓰입니다. 여기에는 봐 둘 만한 것만 옵니다.
          </p>
        </div>

        {unverified.length === 0 ? (
          <div className="empty">
            <p className="mb-2 text-ink">확인할 기록이 없습니다.</p>
            <p className="text-sm">
              아직 아무 도구도 연결하지 않았다면{" "}
              <Link href="/connect" className="link">
                연결하기
              </Link>
              에서 시작하세요.
            </p>
          </div>
        ) : (
          <>
            <div>
              <div className="mb-3 flex items-baseline gap-3">
                <h2 className="text-[15px] font-semibold text-ink">이번 주 표본</h2>
                <span className="faint text-xs">무작위 {sample.length}건 · 기록 품질을 재는 데 씁니다 · 1분</span>
              </div>
              <div className="space-y-3">
                {sample.map((d) => (
                  <Item key={d.id} decision={d} />
                ))}
              </div>
            </div>

            {flagged.length > 0 && (
              <div>
                <div className="mb-3 flex items-baseline gap-3">
                  <h2 className="text-[15px] font-semibold text-ink">봐 둘 만한 것</h2>
                  <span className="faint text-xs">팀에 갈 기록, 거부·수정, 원칙, 뒤집은 결정, 가림, 설명에 판정이 섞인 기록 · {flagged.length}건</span>
                </div>
                <div className="space-y-3">
                  {flagged.map((d) => (
                    <Item key={d.id} decision={d} />
                  ))}
                </div>
              </div>
            )}

            {rest > 0 && (
              <p className="muted text-sm">
                그 밖의 승인 기록 {rest}건은 손댈 일 없이 이미 검색에 쓰이고 있습니다.{" "}
                <Link href="/decisions?unverified=1" className="link">
                  목록 보기
                </Link>
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
