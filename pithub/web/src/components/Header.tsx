import Link from "next/link";

import AuthButton from "@/components/AuthButton";

interface HeaderProps {
  /** 로그인한 사람에게만 보이는 메뉴를 그릴지 */
  signedIn: boolean;
  handle?: string | null;
}

export default function Header({ signedIn, handle }: HeaderProps) {
  return (
    <header className="border-b border-gray-800 px-6 py-3">
      <div className="max-w-5xl mx-auto flex items-center gap-6">
        <Link href="/" className="text-lg font-bold">
          <span className="text-blue-400">pit</span>hub
        </Link>
        {signedIn && (
          <nav className="flex items-center gap-4 text-sm text-gray-400">
            <Link href="/inbox" className="hover:text-white">받은함</Link>
            <Link href="/decisions" className="hover:text-white">내 결정</Link>
            {handle && <Link href={`/u/${handle}`} className="hover:text-white">공개 페이지</Link>}
            <Link href="/connect" className="hover:text-white">연결</Link>
            <Link href="/settings" className="hover:text-white">설정</Link>
          </nav>
        )}
        <div className="ml-auto">
          <AuthButton />
        </div>
      </div>
    </header>
  );
}
