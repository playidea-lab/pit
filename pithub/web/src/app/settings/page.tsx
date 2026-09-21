import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { deleteMyAccount, exportMyData, issueToken, revokeToken } from "@/lib/account-actions";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/settings");
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  const { data: tokens } = await supabase
    .from("api_tokens")
    .select("id, name, created_at, last_used_at, revoked_at")
    .order("created_at", { ascending: false });
  const newToken = (await cookies()).get("pithub_new_token")?.value;

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
          <h2 className="text-lg font-semibold mb-1">로컬 pit 토큰</h2>
          <p className="text-gray-400 text-sm mb-3">
            원문 보존과 감사를 원하는 개발자용 CLI(<code>pit login</code>)에 쓰는 토큰입니다. 발급 직후 한 번만 보입니다.
          </p>
          {newToken && (
            <div className="mb-4 rounded-lg border border-green-800 bg-green-950/40 p-3">
              <p className="text-sm text-green-300 mb-1">새 토큰 — 지금 복사해 두세요. 다시 볼 수 없습니다.</p>
              <code className="block break-all text-sm">{newToken}</code>
              <p className="text-xs text-gray-400 mt-2">
                <code>pit login</code> 을 실행하고 붙여 넣으면 됩니다.
              </p>
            </div>
          )}
          <form action={issueToken} className="flex gap-2 mb-4">
            <input name="name" placeholder="이 기기 이름 (예: 맥북)" className="rounded-lg bg-gray-950 border border-gray-700 px-3 py-2 text-sm" />
            <button className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm">토큰 발급</button>
          </form>
          <ul className="space-y-2 text-sm">
            {(tokens ?? []).map((t) => (
              <li key={t.id} className="flex items-center gap-3 text-gray-300">
                <span className={t.revoked_at ? "line-through text-gray-600" : ""}>{t.name}</span>
                <span className="text-gray-500 text-xs">
                  발급 {new Date(t.created_at).toLocaleDateString("ko-KR")}
                  {t.last_used_at && ` · 마지막 사용 ${new Date(t.last_used_at).toLocaleDateString("ko-KR")}`}
                </span>
                {!t.revoked_at && (
                  <form action={revokeToken} className="ml-auto">
                    <input type="hidden" name="id" value={t.id} />
                    <button className="text-xs text-red-300 hover:underline">폐기</button>
                  </form>
                )}
              </li>
            ))}
          </ul>
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
