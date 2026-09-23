import { redirect } from "next/navigation";

import { formatDate } from "@/components/DecisionCard";
import Header from "@/components/Header";
import { answerTwinQuestion, rateTwinAnswer } from "@/lib/actions";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { listConsults, listPendingQuestions, scoreJudges, type Consult, type TwinQuestion } from "@/lib/twin";

export const dynamic = "force-dynamic";

function Question({ question }: { question: TwinQuestion }) {
  return (
    <form action={answerTwinQuestion} className="card space-y-3">
      <input type="hidden" name="question_id" value={question.id} />
      <div className="faint flex flex-wrap gap-x-3 text-xs">
        <span className="text-ink">{question.asker}</span>
        <span>{formatDate(question.created_at)}</span>
        {question.confidence !== null && <span>트윈 확신도 {question.confidence.toFixed(2)}</span>}
      </div>
      {question.situation && <p className="muted text-sm">{question.situation}</p>}
      <p className="text-[15px] font-medium text-ink">{question.proposal}</p>
      <input name="quote" required placeholder="당신의 답 한 줄 (예: 아니, 시간 분할로)" className="input" />
      <div className="flex flex-wrap gap-2">
        <button name="verdict" value="approve" className="btn btn-secondary h-8 px-3">승인</button>
        <button name="verdict" value="modify" className="btn btn-secondary h-8 px-3">수정해서</button>
        <button name="verdict" value="reject" className="btn btn-primary h-8 px-3">거부</button>
      </div>
    </form>
  );
}

const VERDICT_LABEL = { approve: "승인", modify: "수정", reject: "거부" } as const;

function ConsultRow({ consult }: { consult: Consult }) {
  return (
    <li className="space-y-1.5 py-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-ink">{consult.asker}</span>
        <span className="muted min-w-0 flex-1 truncate">{consult.question}</span>
        <span className={consult.abstained ? "badge badge-modify" : "badge badge-approve"}>
          {consult.abstained ? "기권 → 당신에게" : `트윈: ${VERDICT_LABEL[consult.prediction ?? "reject"]}`}
        </span>
        <span className="faint text-xs">{formatDate(consult.created_at)}</span>
      </div>
      {consult.owner_verdict ? (
        <p className="faint text-xs">당신의 판정: {VERDICT_LABEL[consult.owner_verdict]}</p>
      ) : (
        <form action={rateTwinAnswer} className="flex flex-wrap items-center gap-1.5">
          <input type="hidden" name="consult_id" value={consult.id} />
          <span className="faint mr-1 text-xs">당신이라면?</span>
          {(["approve", "modify", "reject"] as const).map((v) => (
            <button key={v} name="verdict" value={v} className="btn btn-ghost h-7 px-2 text-xs">
              {VERDICT_LABEL[v]}
            </button>
          ))}
        </form>
      )}
    </li>
  );
}

/**
 * 내 트윈 — 동료의 AI가 "당신이라면?"을 물었고 트윈이 확신하지 못해 넘긴 질문, 그리고 모든 자문 기록.
 * 답하면 당신의 결정으로 기록되어(질문이 팀에서 왔으면 팀 범위) 다음부터 트윈이 그것으로 답한다.
 */
export default async function TwinPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/twin");
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");
  const [pending, consults] = await Promise.all([
    listPendingQuestions(supabase, account.github_id),
    listConsults(supabase, account.github_id),
  ]);
  const answered = consults.filter((c) => !c.abstained).length;
  const scores = scoreJudges(consults);

  return (
    <main>
      <Header signedIn />
      <section className="page space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">내 트윈</h1>
          <p className="muted mt-1 text-sm">
            동료의 AI가 &ldquo;당신이라면?&rdquo;을 물으면, 트윈이 당신의 팀 판단을 근거로 답합니다. 확신하지 못하면
            답하지 않고 여기로 넘깁니다. 트윈의 답은 예측일 뿐 당신의 결정이 아닙니다.
          </p>
        </div>

        <div>
          <h2 className="mb-3 text-[15px] font-semibold text-ink">답해 줄 질문 · {pending.length}건</h2>
          {pending.length === 0 ? (
            <div className="empty">트윈이 넘긴 질문이 없습니다.</div>
          ) : (
            <div className="space-y-3">
              {pending.map((q) => (
                <Question key={q.id} question={q} />
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="mb-1 text-[15px] font-semibold text-ink">판정기 성적 · 당신의 채점 기준</h2>
          <p className="muted mb-3 text-xs">
            답은 kNN(서버 안, 무료)이 하고, 팀이 동의했으면 JEV가 같은 질문을 따로 판정해 기록만 합니다. 아래 기록에서
            &ldquo;당신이라면?&rdquo;에 답할수록 어느 판정기가 당신을 더 잘 아는지 드러납니다.
          </p>
          <div className="flex flex-wrap gap-x-8 gap-y-2">
            {scores.map((s) => (
              <div key={s.judge}>
                <p className="label mb-0.5">{s.judge === "knn" ? "kNN (답함)" : "JEV (그림자)"}</p>
                <p className="text-ink">
                  {s.rated === 0 ? "채점 전" : `${s.hits}/${s.rated} · ${Math.round((s.hits / s.rated) * 100)}%`}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-3 text-[15px] font-semibold text-ink">
            자문 기록 · 최근 {consults.length}건 중 트윈이 답한 것 {answered}건
          </h2>
          {consults.length === 0 ? (
            <div className="empty">아직 아무도 당신의 트윈에게 묻지 않았습니다.</div>
          ) : (
            <ul className="card divide-y divide-border">
              {consults.map((c) => (
                <ConsultRow key={c.id} consult={c} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
