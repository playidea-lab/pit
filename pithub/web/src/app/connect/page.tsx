import Link from "next/link";

import CopyBox from "@/components/CopyBox";
import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { siteOrigin } from "@/lib/origin";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { listMyTeams } from "@/lib/teams";

export const dynamic = "force-dynamic";

const MCP_URL_ENV = "NEXT_PUBLIC_PITHUB_MCP_URL";
// claude.ai 처럼 훅이 없는 도구의 전역 지침에 붙이는 문장 — install-hooks.sh 가 훅으로 넣는 것과 같은 뜻
const RECORD_REMINDER =
  "pithub가 연결돼 있으면: 내가 당신의 제안을 거부·수정하거나, 선택지 중에 고르거나, 방향을 승인하면 그 자리에서 pithub record_decision을 한 번 불러 기록해. 내 말은 그대로 인용하고 주제(about)를 붙여. '응/계속' 같은 대답과 새 요청은 기록하지 마.";

/** 기록 누락 줄이기 — AI는 일에 몰두하면 기록 도구를 잊는다(개발 세션 실측 재현율 0%) */
function Reminder({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-2 border-t border-border pt-3">
      <p className="text-ink">기록이 빠지지 않게 (권장, 한 번)</p>
      {children}
    </div>
  );
}

interface PageProps {
  searchParams: Promise<{ joined?: string }>;
}

function Tool({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="card space-y-3">
      <h2 className="text-[15px] font-semibold text-ink">{name}</h2>
      <div className="muted space-y-2 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

/**
 * 연결하기 — 도구마다 한 단계. 주소는 하나다: 팀이 하나뿐인 사람은 서버가 그 팀으로 기록한다.
 * 초대 링크로 막 들어온 사람도 여기로 온다.
 */
export default async function ConnectPage({ searchParams }: PageProps) {
  const { joined } = await searchParams;
  const user = await getUser();
  const supabase = user ? await createServerSupabaseClient() : null;
  const account = supabase ? await getMyAccount(supabase) : null;
  const teams = supabase && account ? await listMyTeams(supabase, account.github_id) : [];
  const url = process.env[MCP_URL_ENV] ?? "(설정되지 않음)";
  const hookInstall = `curl -fsSL ${await siteOrigin()}/install-hooks.sh | sh`;

  return (
    <main>
      <Header signedIn={Boolean(user)} />
      <section className="page space-y-4">
        {joined && (
          <div className="card border-[var(--approve-fg)]/30 bg-[var(--approve-bg)]">
            <p className="text-sm font-medium text-[var(--approve-fg)]">{joined} 팀에 들어왔습니다. 이제 도구 하나만 연결하면 끝입니다.</p>
          </div>
        )}

        <div className="mb-6">
          <h1 className="mb-2 text-2xl font-semibold tracking-tight text-ink">연결하기</h1>
          <p className="muted leading-relaxed">
            쓰는 도구에 아래 주소를 한 번 붙이고, 뜨는 창에서 pithub에 로그인(회사 이메일 또는 GitHub)하면 끝입니다. 그 뒤로는 할 일이 없습니다 — 평소처럼
            일하면 됩니다.
          </p>
          {teams.length > 1 && (
            <p className="mt-2 text-sm text-[var(--modify-fg)]">
              팀이 {teams.length}개입니다. 팀마다 주소가 다릅니다 — 각 팀 페이지의 주소를 쓰세요.
            </p>
          )}
        </div>

        <CopyBox value={url} label="주소 복사" />

        <Tool name="Claude Code">
          <p>터미널에서 한 줄:</p>
          <CopyBox value={`claude mcp add -s user --transport http pithub ${url}`} />
          <p>
            다음에 Claude Code를 열면 <code className="text-ink">/mcp</code> → pithub → 로그인.
          </p>
          <Reminder>
            <p>메시지를 보낼 때마다 AI에게 &ldquo;방금 판단이 있었으면 기록하라&rdquo;는 한 줄을 붙입니다. Codex도 함께 설치됩니다.</p>
            <CopyBox value={hookInstall} />
          </Reminder>
        </Tool>

        <Tool name="claude.ai">
          <p>
            설정 → 커넥터 → <b className="text-ink">커스텀 커넥터 추가</b> → 위 주소 붙여넣기 → 연결 → pithub 로그인.
          </p>
          <Reminder>
            <p>
              claude.ai에는 훅이 없어서 지침으로 대신합니다. 설정 → 일반 → <b className="text-ink">개인 선호 사항</b>에 붙여
              넣으세요.
            </p>
            <CopyBox value={RECORD_REMINDER} />
          </Reminder>
        </Tool>

        <Tool name="Codex">
          <p>터미널:</p>
          <CopyBox value={`codex mcp add pithub --url ${url} && codex mcp login pithub`} />
          <p>
            앱이라면 Settings → MCP servers → Add server → Streamable HTTP에 위 주소.
          </p>
          <Reminder>
            <p>Claude Code와 같은 한 줄입니다(둘 다 있으면 한 번에 설치). Codex를 다음에 열 때 새 훅을 믿을지 물으면 허용하세요.</p>
            <CopyBox value={hookInstall} />
          </Reminder>
        </Tool>

        <Tool name="그 밖의 AI 도구">
          <p>
            MCP를 지원하는 도구면 같은 주소로 연결됩니다. 훅이 없는 도구는 전역 지침(규칙·AGENTS.md 등)에 아래 문장을
            넣으세요.
          </p>
          <CopyBox value={RECORD_REMINDER} />
        </Tool>

        <div className="card space-y-2">
          <h2 className="text-[15px] font-semibold text-ink">잘 붙었는지 확인</h2>
          <p className="muted text-sm">
            AI에게 <b className="text-ink">&ldquo;pithub whoami 불러 줘&rdquo;</b>라고 해 보세요. 팀 이름이 나오면 준비 끝입니다.
          </p>
        </div>

        <div className="card space-y-2">
          <h2 className="text-[15px] font-semibold text-ink">그다음에 일어나는 일</h2>
          <ul className="muted list-disc space-y-1 pl-5 text-sm">
            <li>AI의 제안을 거부하거나 고치거나 방향을 정하면, AI가 그 판단을 조용히 기록합니다. 대화 원문은 보내지 않습니다.</li>
            <li>AI는 제안하기 전에 팀의 판단을 먼저 찾아봅니다. &ldquo;○○이라면?&rdquo;이라고 물으면 트윈이 근거와 함께 답합니다.</li>
            <li>
              기록은 3일 뒤 팀에 보입니다. 그 전에{" "}
              <Link href="/inbox" className="link">
                정리함
              </Link>
              에서 빼거나 고칠 수 있습니다.
            </li>
          </ul>
        </div>
      </section>
    </main>
  );
}
