import Link from "next/link";

import AuthButton from "@/components/AuthButton";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient } from "@/lib/supabase-server";
import { countPendingQuestions } from "@/lib/twin";

interface HeaderProps {
  /** 로그인한 사람에게만 보이는 메뉴를 그릴지 */
  signedIn: boolean;
  handle?: string | null;
}

const TWIN_HREF = "/twin";
const NAV = [
  { href: "/inbox", label: "정리함" },
  { href: "/decisions", label: "내 결정" },
  { href: "/topics", label: "주제" },
  { href: "/teams", label: "팀" },
  { href: TWIN_HREF, label: "내 트윈" },
  { href: "/connect", label: "연결" },
  { href: "/settings", label: "설정" },
];

/** 동료가 내 트윈에게 물었는데 트윈이 답하지 못한 질문 — 주인이 답해야 트윈이 배운다 */
async function pendingTwinQuestions(): Promise<number> {
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  return account ? countPendingQuestions(supabase, account.github_id) : 0;
}

// 좁은 화면에서는 메뉴만 가로로 밀어 본다 — 초대 링크는 대개 폰의 메신저에서 열린다
export default async function Header({ signedIn }: HeaderProps) {
  const waiting = signedIn ? await pendingTwinQuestions() : 0;
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-3xl items-center gap-4 px-4 sm:gap-7 sm:px-6">
        <Link href="/" className="shrink-0 text-[17px] font-semibold tracking-tight text-ink">
          <span className="text-accent">pit</span>hub
        </Link>
        {signedIn && (
          <nav className="flex min-w-0 items-center gap-4 overflow-x-auto whitespace-nowrap text-sm sm:gap-5">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="muted transition-colors hover:text-ink">
                {item.label}
                {item.href === TWIN_HREF && waiting > 0 && (
                  <span className="badge badge-reject ml-1.5" title={`답을 기다리는 질문 ${waiting}건`}>
                    {waiting}
                  </span>
                )}
              </Link>
            ))}
          </nav>
        )}
        <div className="ml-auto shrink-0">
          <AuthButton />
        </div>
      </div>
    </header>
  );
}
