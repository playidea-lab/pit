import Link from "next/link";
import { redirect } from "next/navigation";

import Header from "@/components/Header";
import InboxItem from "@/components/InboxItem";
import { getMyAccount, listInbox } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/inbox");

  const supabase = await createServerSupabaseClient();
  const [account, inbox] = await Promise.all([getMyAccount(supabase), listInbox(supabase)]);

  return (
    <main>
      <Header signedIn handle={account?.github_login} />
      <section className="page">
        <div className="mb-6 flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">받은함</h1>
          <span className="muted text-sm">{inbox.length}건 대기</span>
        </div>

        {inbox.length === 0 ? (
          <div className="empty">
            <p className="mb-2 text-ink">검토할 결정이 없습니다.</p>
            <p className="text-sm">
              아직 아무 도구도 연결하지 않았다면{" "}
              <Link href="/connect" className="link">
                연결하기
              </Link>
              에서 시작하세요.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {inbox.map((decision) => (
              <InboxItem key={decision.id} decision={decision} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
