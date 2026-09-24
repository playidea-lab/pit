import Link from "next/link";

import Header from "@/components/Header";
import Checklist from "@/components/home/Checklist";
import Landing from "@/components/home/Landing";
import TeamPulse from "@/components/home/TeamPulse";
import { getMyAccount, type Account } from "@/lib/decisions";
import { loadHome, type HomeData } from "@/lib/home";
import { siteOrigin } from "@/lib/origin";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

function Stat({ label, value, href, alert = false }: { label: string; value: number; href: string; alert?: boolean }) {
  return (
    <Link href={href} className="card-link block">
      <p className="label mb-1">{label}</p>
      <p className={`text-2xl font-semibold ${alert && value > 0 ? "text-[var(--reject-fg)]" : "text-ink"}`}>{value}</p>
    </Link>
  );
}

function MyStatus({ account, data }: { account: Account; data: HomeData }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{account.github_login}</h1>
        {data.invites.length > 0 && (
          <Link href="/teams" className="badge badge-modify">
            팀 초대·요청 {data.invites.length}
          </Link>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="이번 주 내 기록" value={data.thisWeek} href="/decisions" />
        <Stat label="정리함" value={data.unverified} href="/inbox" />
        <Stat label="트윈이 넘긴 질문" value={data.twinQuestions} href="/twin" alert />
      </div>
    </div>
  );
}

/**
 * 홈 — 로그인 전에는 소개, 로그인 뒤에는 할 일: 시작 체크리스트 · 내 현황 · 팀 현황.
 * 소개는 로그인 뒤에도 /about 에서 본다.
 */
export default async function HomePage() {
  const user = await getUser();
  const supabase = user ? await createServerSupabaseClient() : null;
  const account = supabase ? await getMyAccount(supabase) : null;

  if (!supabase || !account) {
    return (
      <main>
        <Header signedIn={Boolean(user)} />
        <section className="page">
          <Landing signedIn={Boolean(user)} />
        </section>
      </main>
    );
  }

  const data = await loadHome(supabase, account);
  const hookInstall = `curl -fsSL ${await siteOrigin()}/install-hooks.sh | sh`;
  return (
    <main>
      <Header signedIn handle={account.github_login} />
      <section className="page space-y-6">
        <MyStatus account={account} data={data} />
        <Checklist data={data} hookInstall={hookInstall} />
        {data.teams.map((team) => (
          <TeamPulse key={team.id} supabase={supabase} team={team} />
        ))}
        <p className="faint text-xs">
          <Link href="/about" className="link">
            pithub는 어떻게 동작하나
          </Link>
        </p>
      </section>
    </main>
  );
}
