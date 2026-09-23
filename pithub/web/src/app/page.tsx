import Link from "next/link";

import Header from "@/components/Header";
import { getMyAccount, type Account } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { listMyInvites, listMyTeams } from "@/lib/teams";

export const dynamic = "force-dynamic";

const DAYS_IN_WEEK = 7;
const MS_PER_DAY = 86_400_000;

/** 제품 설명 전부 — 두 장면. 스크린샷 대신 글로 두어 실제 화면과 어긋날 일이 없다. */
const SCENES = [
  {
    when: "오늘, 내 세션",
    lines: [
      ["AI", "평가를 무작위 분할로 하겠습니다."],
      ["나", "아니, 시간 분할로 해. 미래가 새."],
      ["", "· pithub 기록됨 — 거부 · 시간 분할"],
    ],
  },
  {
    when: "다음 주, 동료의 세션",
    lines: [
      ["AI", "평가 분할을 정하기 전에 팀 기록을 봤습니다."],
      ["AI", "지난주 changmin이 무작위 분할을 기각했습니다 — 시간 분할로 갑니다."],
      ["동료", "ㅇㅇ"],
    ],
  },
] as const;

/** 들어온 사람이 셋 중 누구인지 — 각자 할 일만 */
const ROLES = [
  {
    title: "혼자 쓴다",
    body: "claude.ai · Claude Code · Codex 어디든 커넥터 하나를 붙인다. 기록은 본인만 본다.",
    cta: ["연결하기", "/connect"],
  },
  {
    title: "팀에 초대받았다",
    body: "팀 저장소를 받아 세션을 열면 로그인만 물어본다. 그 뒤로는 평소대로 일한다. 첫 기록이 곧 가입 요청이다.",
    cta: ["팀 보기", "/teams"],
  },
  {
    title: "팀을 만든다",
    body: "팀을 만들고 저장소에 .mcp.json 한 줄을 커밋한다. 팀원은 승인 한 번으로 들어온다.",
    cta: ["팀 만들기", "/teams"],
  },
] as const;

/** 경계 — 정직한 한계를 먼저 말한다 */
const POINTS = [
  ["원문은 나가지 않습니다", "대화 자체는 저장하지 않습니다. 결정 한 건의 요약과 당신의 말 한 줄만 받습니다."],
  ["기본은 비공개", "기록은 본인만 봅니다. 팀에 보이는 것은 당신이 “맞음”을 누른 결정뿐입니다."],
  ["빠지기도, 잘못 붙기도 합니다", "기록은 AI의 재량입니다. 그래서 확인이 있고, 확인은 쓰는 순간에만 합니다."],
  ["언제든 지웁니다", "결정 하나든 계정 전체든, 삭제하면 정말로 사라집니다."],
] as const;

function Scene({ when, lines }: (typeof SCENES)[number]) {
  return (
    <div className="code">
      <p className="faint mb-3 text-xs">{when}</p>
      {lines.map(([who, text], i) => (
        <p key={i} className={who ? "mb-1.5" : "faint mt-3 text-xs"}>
          {who && <span className="muted mr-2">{who}</span>}
          <span className={who === "나" || who === "동료" ? "text-accent" : ""}>{text}</span>
        </p>
      ))}
    </div>
  );
}

// 렌더 중 시계를 읽는 건 서버 요청 시점의 값이 목적이다. react-hooks/purity 가 컴포넌트
// 본문의 Date.now() 를 막으므로 컴포넌트 밖 함수로 둔다.
function weekAgoIso(): string {
  return new Date(Date.now() - DAYS_IN_WEEK * MS_PER_DAY).toISOString();
}

async function Status({ account }: { account: Account }) {
  const supabase = await createServerSupabaseClient();
  const weekAgo = weekAgoIso();
  const [{ count: thisWeek }, { count: unverified }, teams, invites] = await Promise.all([
    supabase.from("decisions").select("id", { count: "exact", head: true }).neq("status", "discarded").gte("decided_at", weekAgo),
    supabase.from("decisions").select("id", { count: "exact", head: true }).eq("status", "draft"),
    listMyTeams(supabase, account.github_id),
    listMyInvites(supabase, account.github_id),
  ]);

  return (
    <div className="card">
      <p className="muted mb-3 text-sm">{account.github_login}</p>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <Stat label="이번 주 기록" value={thisWeek ?? 0} href="/decisions" />
        <Stat label="확인 대기" value={unverified ?? 0} href="/inbox" />
        <div>
          <p className="label mb-1">팀</p>
          {teams.length === 0 && invites.length === 0 ? (
            <Link href="/teams" className="link text-lg">
              없음
            </Link>
          ) : (
            <p className="text-lg text-ink">
              {teams.map((t) => (
                <Link key={t.id} href={`/t/${t.slug}`} className="link mr-2">
                  {t.slug}
                </Link>
              ))}
              {invites.length > 0 && (
                <Link href="/teams" className="badge badge-modify align-middle">
                  초대·요청 {invites.length}
                </Link>
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, href }: { label: string; value: number; href: string }) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <Link href={href} className="text-lg text-ink hover:text-accent">
        {value}건
      </Link>
    </div>
  );
}

export default async function HomePage() {
  const user = await getUser();
  const account = user ? await getMyAccount(await createServerSupabaseClient()) : null;

  return (
    <main>
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="page space-y-16 pt-12">
        {account && <Status account={account} />}

        <div className={account ? "pt-4" : "pt-8"}>
          <p className="label mb-4">pithub</p>
          <h1 className="mb-5 text-[40px] font-semibold leading-[1.15] tracking-tight text-ink">
            AI가 같은 실수를
            <br />
            <span className="text-accent">두 번 하지 않게</span>
          </h1>
          <p className="muted max-w-xl text-[17px] leading-relaxed">
            당신이 거부하고 고치고 방향을 정한 순간을 AI가 스스로 기록합니다. 다음 세션의 AI는 — 당신의 것이든
            팀원의 것이든 — 제안하기 전에 그 기록을 먼저 찾아봅니다.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {SCENES.map((scene) => (
            <Scene key={scene.when} {...scene} />
          ))}
        </div>

        <div>
          <h2 className="mb-5 text-[15px] font-semibold text-ink">당신은 누구입니까</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {ROLES.map(({ title, body, cta }) => (
              <div key={title} className="card flex flex-col">
                <p className="mb-1.5 font-medium text-ink">{title}</p>
                <p className="muted mb-4 flex-1 text-sm leading-relaxed">{body}</p>
                <Link href={cta[1]} className="btn btn-secondary h-9 self-start px-4">
                  {cta[0]}
                </Link>
              </div>
            ))}
          </div>
        </div>

        <ul className="grid gap-8 sm:grid-cols-2">
          {POINTS.map(([title, body]) => (
            <li key={title}>
              <p className="mb-1.5 font-medium text-ink">{title}</p>
              <p className="muted text-sm leading-relaxed">{body}</p>
            </li>
          ))}
        </ul>

        <p className="faint text-xs">
          오픈소스(AGPL-3.0) —{" "}
          <a href="https://github.com/playidea-lab/pit" className="link">
            github.com/playidea-lab/pit
          </a>
          . 직접 돌릴 수도 있습니다.
        </p>
      </section>
    </main>
  );
}
