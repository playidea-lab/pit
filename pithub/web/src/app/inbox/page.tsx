import Link from "next/link";
import { redirect } from "next/navigation";

import { VerdictBadge, formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import VerifyBar from "@/components/VerifyBar";
import { resolveConflict } from "@/lib/actions";
import {
  getMyAccount,
  leaksVerdict,
  listUnverified,
  needsAttention,
  teamShareAt,
  weeklySample,
  type Decision,
} from "@/lib/decisions";
import { listConflictCandidates, type ConflictCandidate } from "@/lib/graph";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function shareDate(decision: Decision): string {
  return teamShareAt(decision)?.toLocaleDateString("ko-KR") ?? "";
}

function Item({ decision }: { decision: Decision }) {
  const redacted = Object.values(decision.redactions).reduce((a, b) => a + b, 0);
  return (
    <article className="card">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="faint">{formatDate(decision.decided_at)}</span>
        {decision.source.project && <span className="faint">{decision.source.project}</span>}
        {decision.visibility === "team" && (
          <span className="badge badge-choice">팀 · {shareDate(decision)} 자동으로 보임 · 빼려면 자세히</span>
        )}
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

function Side({ label, decision }: { label: string; decision: ConflictCandidate["a"] }) {
  return (
    <Link href={`/d/${decision.id}`} className="block rounded-lg border border-border p-3 hover:bg-[var(--accent-soft)]/30">
      <div className="mb-1 flex items-center gap-2 text-xs">
        <VerdictBadge verdict={decision.verdict} chosen={decision.chosen} />
        <span className="text-ink">{decision.mine ? "나" : decision.author}</span>
        <span className="faint">{formatDate(decision.decided_at)}</span>
        <span className="faint ml-auto">{label}</span>
      </div>
      <p className="text-sm text-ink">{decision.proposal}</p>
      <p className="muted mt-1 text-xs">&ldquo;{decision.human_quote}&rdquo;</p>
    </Link>
  );
}

function Conflict({ conflict }: { conflict: ConflictCandidate }) {
  return (
    <article className="card space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Side label="A" decision={conflict.a} />
        <Side label="B" decision={conflict.b} />
      </div>
      <form action={resolveConflict} className="flex flex-wrap gap-2">
        <input type="hidden" name="link_id" value={conflict.id} />
        <button name="action" value="confirm" className="btn btn-primary h-8 px-3">충돌 맞음 · 이야기가 필요</button>
        <button name="action" value="supersede" className="btn btn-secondary h-8 px-3">나중 결정이 먼저 것을 뒤집음</button>
        <button name="action" value="dismiss" className="btn btn-ghost h-8 px-3">충돌 아님</button>
      </form>
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
  const conflicts = account ? await listConflictCandidates(supabase, account.github_id) : [];
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

        {conflicts.length > 0 && (
          <div>
            <div className="mb-3 flex items-baseline gap-3">
              <h2 className="text-[15px] font-semibold text-ink">충돌 후보</h2>
              <span className="faint text-xs">
                같은 주제에서 반대로 판정된 결정 · {conflicts.length}건 · 어느 쪽이 서는지 정해 두면 팀의 AI가 헷갈리지 않습니다
              </span>
            </div>
            <div className="space-y-3">
              {conflicts.map((c) => (
                <Conflict key={c.id} conflict={c} />
              ))}
            </div>
          </div>
        )}

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
                  <span className="faint text-xs">곧 팀에 보일 기록, 거부·수정, 원칙, 뒤집은 결정, 가림, 설명에 판정이 섞인 기록 · {flagged.length}건</span>
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
