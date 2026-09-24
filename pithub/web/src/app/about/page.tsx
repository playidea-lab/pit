import Header from "@/components/Header";
import Landing from "@/components/home/Landing";
import { getUser } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

/** 소개 — 로그인한 사람도 동료에게 설명할 때 여기로 보낸다 */
export default async function AboutPage() {
  const user = await getUser();
  return (
    <main>
      <Header signedIn={Boolean(user)} />
      <section className="page">
        <Landing signedIn={Boolean(user)} />
      </section>
    </main>
  );
}
