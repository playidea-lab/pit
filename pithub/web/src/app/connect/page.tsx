import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

const MCP_URL_ENV = "NEXT_PUBLIC_PITHUB_MCP_URL";

const PROMPT_SNIPPET =
  "When I approve, modify, or reject something you proposed, call pithub's record_decision right away, " +
  "quoting my words verbatim. Rejections and corrections matter most. Before proposing an approach on a topic " +
  "I may have decided before, check search_my_decisions.";

function Code({ children }: { children: string }) {
  return (
    <pre className="code">
      <code>{children}</code>
    </pre>
  );
}

function Step({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h2 className="mb-2 text-[15px] font-semibold text-ink">{title}</h2>
      <div className="muted text-sm leading-relaxed">{children}</div>
    </div>
  );
}

export default async function ConnectPage() {
  const user = await getUser();
  const account = user ? await getMyAccount(await createServerSupabaseClient()) : null;
  const mcpUrl = process.env[MCP_URL_ENV] ?? "(설정되지 않음)";

  return (
    <main>
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="page space-y-4">
        <div className="mb-8">
          <h1 className="mb-2 text-2xl font-semibold tracking-tight text-ink">연결하기</h1>
          <p className="muted leading-relaxed">
            쓰는 도구에 아래 주소를 한 번 추가하고 GitHub로 로그인하면 끝입니다. 이후에는 아무것도 할 필요가
            없습니다. 결정이 내려질 때 AI가 스스로 기록합니다.
          </p>
          <Code>{mcpUrl}</Code>
        </div>

        <Step title="claude.ai">
          설정 → 커넥터 → <b className="text-ink">커스텀 커넥터 추가</b>에 위 주소를 넣고, 열리는 화면에서 GitHub로
          로그인합니다.
        </Step>

        <Step title="Claude Code">
          <Code>{`claude mcp add --transport http pithub ${mcpUrl}`}</Code>
          <p className="mt-2">
            세션 안에서 <code className="text-ink">/mcp</code> → pithub → Authenticate.
          </p>
        </Step>

        <Step title="Codex">
          앱: Settings → MCP servers → Add server → Streamable HTTP에 위 주소. 터미널이라면:
          <Code>{`codex mcp add pithub --url ${mcpUrl}\ncodex mcp login pithub`}</Code>
        </Step>

        <Step title="팀으로 기록하려면">
          팀 저장소에는 개인 주소 대신 <b className="text-ink">팀 커넥터 주소</b>(<code className="text-ink">…/t/&lt;팀&gt;/mcp</code>)를
          <code className="text-ink">.mcp.json</code>으로 커밋해 둡니다. 그 저장소에서 일하는 팀원의 결정은 아무것도 고르지
          않아도 팀 범위로 기록되고, 각자 확인한 것만 팀에 보입니다. 주소는 팀 페이지에 있습니다.
        </Step>

        <Step title="기록을 더 잘 남기게 하려면 (선택)">
          도구를 언제 부를지는 AI가 정합니다. 특히 &ldquo;아니, 그거 말고&rdquo; 같은 거부는 빠지기 쉽습니다. 아래
          문장을 claude.ai의 프로필 지침이나 프로젝트의 <code className="text-ink">CLAUDE.md</code>,{" "}
          <code className="text-ink">AGENTS.md</code>에 붙여 두면 놓치는 일이 줄어듭니다.
          <Code>{PROMPT_SNIPPET}</Code>
        </Step>
      </section>
    </main>
  );
}
