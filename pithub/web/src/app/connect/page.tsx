import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

const MCP_URL_ENV = "NEXT_PUBLIC_PITHUB_MCP_URL";

function Code({ children }: { children: string }) {
  return (
    <pre className="mt-2 rounded-lg bg-gray-900 border border-gray-800 p-3 text-sm overflow-x-auto">
      <code>{children}</code>
    </pre>
  );
}

export default async function ConnectPage() {
  const user = await getUser();
  const account = user ? await getMyAccount(await createServerSupabaseClient()) : null;
  const mcpUrl = process.env[MCP_URL_ENV] ?? "(설정되지 않음)";

  return (
    <main className="min-h-screen">
      <Header signedIn={Boolean(user)} handle={account?.github_login} />
      <section className="max-w-3xl mx-auto px-6 py-12 space-y-10">
        <div>
          <h1 className="text-2xl font-bold mb-2">연결하기</h1>
          <p className="text-gray-400">
            쓰는 도구에 아래 주소를 한 번 추가하고 GitHub로 로그인하면 끝입니다. 이후에는 아무것도 할 필요가
            없습니다. 결정이 내려질 때 AI가 스스로 기록합니다.
          </p>
          <Code>{mcpUrl}</Code>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">claude.ai</h2>
          <p className="text-gray-400 text-sm">
            설정 → 커넥터 → <b>커스텀 커넥터 추가</b>에 위 주소를 넣고, 열리는 화면에서 GitHub로 로그인합니다.
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">Claude Code</h2>
          <Code>{`claude mcp add --transport http pithub ${mcpUrl}`}</Code>
          <p className="text-gray-400 text-sm mt-2">세션 안에서 <code>/mcp</code> → pithub → Authenticate.</p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">Codex</h2>
          <p className="text-gray-400 text-sm">
            앱: Settings → MCP servers → Add server → Streamable HTTP에 위 주소. 터미널이라면:
          </p>
          <Code>{`codex mcp add pithub --url ${mcpUrl}\ncodex mcp login pithub`}</Code>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-1">기록을 더 잘 남기게 하려면 (선택)</h2>
          <p className="text-gray-400 text-sm">
            도구를 언제 부를지는 AI가 정합니다. 특히 &ldquo;아니, 그거 말고&rdquo; 같은 거부는 빠지기 쉽습니다.
            아래 문장을 claude.ai의 프로필 지침, 프로젝트의 <code>CLAUDE.md</code>나 <code>AGENTS.md</code>에
            붙여 두면 놓치는 일이 줄어듭니다.
          </p>
          <Code>{`When I approve, modify, or reject something you proposed, call pithub's record_decision right away, quoting my words verbatim. Rejections and corrections matter most. Before proposing an approach on a topic I may have decided before, check search_my_decisions.`}</Code>
        </div>
      </section>
    </main>
  );
}
