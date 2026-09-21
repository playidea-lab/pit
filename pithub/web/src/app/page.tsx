import Link from "next/link";

import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export default async function HomePage() {
  const user = await getUser();
  const account = user ? await getMyAccount(await createServerSupabaseClient()) : null;

  return (
    <main className="min-h-screen">
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-20">
        <h1 className="text-4xl font-bold mb-4">
          AI와 일하며 내린 결정을, <span className="text-blue-400">기록</span>한다
        </h1>
        <p className="text-lg text-gray-400 mb-10">
          claude.ai · Claude Code · Codex에 pithub를 연결하면, 당신이 제안을 승인하고 고치고 거부한 순간이
          받은함에 쌓입니다. 하루 몇 분 검토해 확정하고, 원하는 것만 공개하세요.
          다음 세션의 AI는 당신이 예전에 어떻게 결정했는지 찾아볼 수 있습니다.
        </p>
        <div className="flex gap-4">
          <Link href="/connect" className="px-5 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 font-medium">
            연결하기
          </Link>
          {user && (
            <Link href="/inbox" className="px-5 py-3 rounded-lg bg-gray-800 hover:bg-gray-700 font-medium">
              받은함 열기
            </Link>
          )}
        </div>
        <ul className="mt-16 grid gap-6 sm:grid-cols-3 text-sm text-gray-400">
          <li>
            <p className="text-gray-100 font-medium mb-1">원문은 나가지 않습니다</p>
            대화 자체는 저장하지 않습니다. 결정 한 건의 요약과 당신의 말 한 줄만 받습니다.
          </li>
          <li>
            <p className="text-gray-100 font-medium mb-1">기본은 비공개</p>
            받은함은 본인만 봅니다. 확정한 뒤 결정마다 공개 여부를 정합니다.
          </li>
          <li>
            <p className="text-gray-100 font-medium mb-1">언제든 지웁니다</p>
            결정 하나든 계정 전체든, 삭제하면 정말로 사라집니다.
          </li>
        </ul>
      </section>
    </main>
  );
}
