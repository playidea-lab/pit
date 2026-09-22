import Link from "next/link";

import AuthButton from "@/components/AuthButton";

interface HeaderProps {
  /** 로그인한 사람에게만 보이는 메뉴를 그릴지 */
  signedIn: boolean;
  handle?: string | null;
}

const NAV = [
  { href: "/inbox", label: "받은함" },
  { href: "/decisions", label: "내 결정" },
  { href: "/connect", label: "연결" },
  { href: "/settings", label: "설정" },
];

export default function Header({ signedIn, handle }: HeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-3xl items-center gap-7 px-6">
        <Link href="/" className="text-[17px] font-semibold tracking-tight text-ink">
          <span className="text-accent">pit</span>hub
        </Link>
        {signedIn && (
          <nav className="flex items-center gap-5 text-sm">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="muted transition-colors hover:text-ink">
                {item.label}
              </Link>
            ))}
            {handle && (
              <Link href={`/u/${handle}`} className="muted transition-colors hover:text-ink">
                공개 페이지
              </Link>
            )}
          </nav>
        )}
        <div className="ml-auto">
          <AuthButton />
        </div>
      </div>
    </header>
  );
}
