import Link from "next/link";

import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

const POINTS = [
  ["원문은 나가지 않습니다", "대화 자체는 저장하지 않습니다. 결정 한 건의 요약과 당신의 말 한 줄만 받습니다."],
  ["기본은 비공개", "받은함은 본인만 봅니다. 확정한 뒤 결정마다 공개 여부를 정합니다."],
  ["언제든 지웁니다", "결정 하나든 계정 전체든, 삭제하면 정말로 사라집니다."],
];

export default async function HomePage() {
  const user = await getUser();
  const account = user ? await getMyAccount(await createServerSupabaseClient()) : null;

  return (
    <main>
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="page pt-20">
        <p className="label mb-4">pithub</p>
        <h1 className="mb-5 text-[40px] font-semibold leading-[1.15] tracking-tight text-ink">
          AI와 일하며 내린 결정을,
          <br />
          <span className="text-accent">왜 그렇게 정했는지</span>까지 남긴다
        </h1>
        <p className="muted mb-10 max-w-xl text-[17px] leading-relaxed">
          claude.ai · Claude Code · Codex에 pithub를 연결하면, 당신이 제안을 승인하고 고치고 거부한 순간이
          받은함에 쌓입니다. 하루 몇 분 검토해 확정하고, 원하는 것만 공개하세요. 다음 세션의 AI는 당신이
          예전에 어떻게 결정했는지 찾아볼 수 있습니다.
        </p>
        <div className="flex gap-2">
          <Link href="/connect" className="btn btn-primary h-10 px-5">
            연결하기
          </Link>
          {user && (
            <Link href="/inbox" className="btn btn-secondary h-10 px-5">
              받은함 열기
            </Link>
          )}
        </div>
        <ul className="mt-20 grid gap-8 sm:grid-cols-3">
          {POINTS.map(([title, body]) => (
            <li key={title}>
              <p className="mb-1.5 font-medium text-ink">{title}</p>
              <p className="muted text-sm leading-relaxed">{body}</p>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
