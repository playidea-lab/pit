import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { deleteMyAccount, exportMyData, issueToken, revokeToken } from "@/lib/account-actions";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { usageSummary } from "@/lib/usage";

export const dynamic = "force-dynamic";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="label mb-0.5">{label}</p>
      <p className="text-ink">{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h2 className="mb-2 text-[15px] font-semibold text-ink">{title}</h2>
      {children}
    </div>
  );
}

export default async function SettingsPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/settings");
  const supabase = await createServerSupabaseClient();
  const [account, usage] = await Promise.all([getMyAccount(supabase), usageSummary(supabase)]);
  const usedPct = usage.returned === 0 ? null : Math.round((usage.used / usage.returned) * 100);
  const { data: tokens } = await supabase
    .from("api_tokens")
    .select("id, name, created_at, last_used_at, revoked_at")
    .order("created_at", { ascending: false });
  const newToken = (await cookies()).get("pithub_new_token")?.value;

  return (
    <main>
      <Header signedIn handle={account?.github_login} />
      <section className="page space-y-4">
        <h1 className="mb-6 text-2xl font-semibold tracking-tight text-ink">설정</h1>

        <Section title="계정">
          <p className="muted text-sm">
            GitHub <b className="text-ink">{account?.github_login ?? "-"}</b> 로 로그인돼 있습니다.
          </p>
        </Section>

        <Section title={`사용량 · 최근 ${usage.days}일`}>
          <p className="muted mb-3 text-sm">
            AI가 pithub를 얼마나 부르고, 돌려준 결과를 실제로 읽었는지. 검색이 잦은데 읽힌 비율이 낮으면 토큰만
            쓰는 것입니다.
          </p>
          <div className="mb-3 flex flex-wrap gap-x-8 gap-y-2">
            <Stat label="검색" value={`${usage.searches}회`} />
            <Stat label="돌려준 결과" value={`${usage.returned}건`} />
            <Stat label="실제로 읽힘" value={usedPct === null ? "-" : `${usage.used}건 · ${usedPct}%`} />
            <Stat label="기록" value={`${usage.records}건`} />
          </div>
          {usage.byClient.length > 0 && (
            <ul className="faint text-xs">
              {usage.byClient.map((c) => (
                <li key={c.client}>
                  {c.client} — 검색 {c.searches} · 기록 {c.records}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="내 데이터 내려받기">
          <p className="muted mb-3 text-sm">확정·초안·버린 것을 포함한 모든 결정을 JSON으로 받습니다.</p>
          <form action={exportMyData}>
            <button className="btn btn-secondary">JSON 내려받기</button>
          </form>
        </Section>

        <Section title="로컬 pit 토큰">
          <p className="muted mb-3 text-sm">
            원문 보존과 감사를 원하는 개발자용 CLI(<code className="text-ink">pit login</code>)에 쓰는 토큰입니다. 발급
            직후 한 번만 보입니다.
          </p>
          {newToken && (
            <div className="mb-4 rounded-lg border border-[var(--approve-fg)]/30 bg-[var(--approve-bg)] p-3">
              <p className="mb-1 text-sm font-medium text-[var(--approve-fg)]">
                새 토큰 — 지금 복사해 두세요. 다시 볼 수 없습니다.
              </p>
              <code className="block break-all font-mono text-sm text-ink">{newToken}</code>
              <p className="muted mt-2 text-xs">
                <code>pit login</code> 을 실행하고 붙여 넣으면 됩니다.
              </p>
            </div>
          )}
          <form action={issueToken} className="mb-4 flex gap-2">
            <input name="name" placeholder="이 기기 이름 (예: 맥북)" className="input max-w-xs" />
            <button className="btn btn-secondary shrink-0">토큰 발급</button>
          </form>
          {(tokens ?? []).length > 0 && (
            <ul className="divide-y divide-border text-sm">
              {(tokens ?? []).map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-2">
                  <span className={t.revoked_at ? "faint line-through" : "text-ink"}>{t.name}</span>
                  <span className="faint text-xs">
                    발급 {new Date(t.created_at).toLocaleDateString("ko-KR")}
                    {t.last_used_at && ` · 마지막 사용 ${new Date(t.last_used_at).toLocaleDateString("ko-KR")}`}
                  </span>
                  {!t.revoked_at && (
                    <form action={revokeToken} className="ml-auto">
                      <input type="hidden" name="id" value={t.id} />
                      <button className="btn btn-danger h-7 px-2 text-xs">폐기</button>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <div className="card border-[var(--reject-fg)]/30">
          <h2 className="mb-2 text-[15px] font-semibold text-[var(--reject-fg)]">계정 삭제</h2>
          <p className="muted mb-3 text-sm">
            본인만 보던 결정, 아직 팀에 보이기 전인 결정, 검토 이력, 토큰이 지워지고 되돌릴 수 없습니다.
            <b className="text-ink"> 이미 팀에 보인 결정은 회사의 기록이라 남습니다</b> — 지우려면 팀 소유자에게 요청하세요.
            확인을 위해 GitHub 아이디를 입력하세요.
          </p>
          <form action={deleteMyAccount} className="flex gap-2">
            <input name="confirm" placeholder={account?.github_login ?? ""} className="input max-w-xs" />
            <button className="btn btn-danger shrink-0 border-[var(--reject-fg)]/40">영구 삭제</button>
          </form>
        </div>
      </section>
    </main>
  );
}
