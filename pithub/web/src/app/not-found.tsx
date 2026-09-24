import Link from "next/link";

import Header from "@/components/Header";
import { getUser } from "@/lib/supabase-server";

/** 없는 주소이거나, 볼 권한이 없는 기록 — RLS 때문에 둘은 구분되지 않는다(구분하면 존재가 새어 나간다) */
export default async function NotFound() {
  const user = await getUser();
  return (
    <main>
      <Header signedIn={Boolean(user)} />
      <section className="page space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">찾을 수 없습니다</h1>
        <p className="muted text-sm">
          주소가 잘못됐거나, 이 기록을 볼 수 있는 사람이 아닙니다. 팀 기록이라면 팀에 들어간 뒤 다시 열어 보세요.
        </p>
        <div className="flex gap-2">
          <Link href="/" className="btn btn-primary">
            처음으로
          </Link>
          {!user && (
            <Link href="/login" className="btn btn-secondary">
              로그인
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
