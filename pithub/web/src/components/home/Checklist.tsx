import Link from "next/link";

import CopyBox from "@/components/CopyBox";
import type { HomeData } from "@/lib/home";

interface Step {
  title: string;
  body: string;
  done: boolean | null; // null = 서버가 확인할 수 없는 단계 (권장)
  href?: string;
  cta?: string;
}

function steps(data: HomeData): Step[] {
  return [
    { title: "팀에 들어오기", body: "초대 링크를 누르면 바로 팀원이 됩니다. 관리자라면 팀을 만들고 링크를 팀 채널에 붙이세요.", done: data.teams.length > 0, href: "/teams", cta: "팀" },
    { title: "쓰는 AI 도구 연결", body: "Claude Code · Codex · claude.ai 중 쓰는 곳에 주소 하나를 붙입니다.", done: data.recorded > 0 || data.searched > 0, href: "/connect", cta: "연결하기" },
    { title: "기록이 빠지지 않게", body: "AI는 일에 몰두하면 기록을 잊습니다. Claude Code · Codex는 한 줄로 상기 훅을 겁니다.", done: null },
    { title: "첫 판단이 기록됨", body: "평소처럼 일하다 AI의 제안을 거부하거나 고치면 여기 체크됩니다.", done: data.recorded > 0, href: "/inbox", cta: "정리함" },
  ];
}

/** 시작 체크리스트 — 확인 가능한 단계가 모두 끝나면 사라진다 */
export default function Checklist({ data, hookInstall }: { data: HomeData; hookInstall: string }) {
  const list = steps(data);
  if (list.every((s) => s.done !== false)) return null;
  const doneCount = list.filter((s) => s.done).length;
  const verifiable = list.filter((s) => s.done !== null).length;
  return (
    <div className="card space-y-4">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[15px] font-semibold text-ink">시작하기</h2>
        <span className="faint text-xs">
          {doneCount}/{verifiable} 완료 · 끝나면 이 칸은 사라집니다
        </span>
      </div>
      <ol className="space-y-3">
        {list.map((s) => (
          <li key={s.title} className="flex gap-3">
            <span
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] ${
                s.done ? "bg-[var(--approve-bg)] text-[var(--approve-fg)]" : "border border-[var(--border-strong)] text-faint"
              }`}
            >
              {s.done ? "✓" : ""}
            </span>
            <div className="min-w-0 flex-1 space-y-1">
              <p className={s.done ? "muted text-sm line-through" : "text-sm text-ink"}>
                {s.title}
                {s.done === null && <span className="faint ml-2 text-xs">권장 · 한 번</span>}
              </p>
              {!s.done && <p className="muted text-xs leading-relaxed">{s.body}</p>}
              {s.done === null && <CopyBox value={hookInstall} />}
            </div>
            {!s.done && s.href && (
              <Link href={s.href} className="btn btn-secondary h-8 shrink-0 self-start px-3">
                {s.cta}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
