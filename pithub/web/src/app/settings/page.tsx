import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { exportMyData, deleteMyAccount } from "@/lib/account-actions";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/settings");
  const account = await getMyAccount(await createServerSupabaseClient());

  return (
    <main className="min-h-screen">
      <Header signedIn handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-10 space-y-10">
        <h1 className="text-2xl font-bold">설정</h1>

        <div>
          <h2 className="text-lg font-semibold mb-1">계정</h2>
          <p className="text-gray-400 text-sm">
            GitHub <b>{account?.github_login ?? "-"}</b> (id {account?.github_id ?? "-"})로 로그인돼 있습니다.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">내 데이터 내려받기</h2>
          <p className="text-gray-400 text-sm mb-3">확정·초안·버린 것을 포함한 모든 결정을 JSON으로 받습니다.</p>
          <form action={exportMyData}>
            <button className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm">JSON 내려받기</button>
          </form>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">로컬 pit 연동</h2>
          <p className="text-gray-400 text-sm">
            원문 보존과 감사를 원하는 개발자용 CLI의 토큰 발급은 다음 단계에서 열립니다.
          </p>
        </div>

        <div className="border border-red-900/60 rounded-lg p-4">
          <h2 className="text-lg font-semibold mb-1 text-red-300">계정과 모든 결정 삭제</h2>
          <p className="text-gray-400 text-sm mb-3">
            결정, 검토 이력, 토큰이 모두 지워지고 되돌릴 수 없습니다. 확인을 위해 GitHub 아이디를 입력하세요.
          </p>
          <form action={deleteMyAccount} className="flex gap-2">
            <input
              name="confirm"
              placeholder={account?.github_login ?? ""}
              className="rounded-lg bg-gray-950 border border-gray-700 px-3 py-2 text-sm"
            />
            <button className="px-4 py-2 rounded-lg bg-red-900/60 hover:bg-red-800 text-sm text-red-100">
              영구 삭제
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
