import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import DecisionCard from "@/components/DecisionCard";
import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import {
  approveMember,
  erasePersona,
  inviteMember,
  leaveTeam,
  removeMember,
  setJudgeConsent,
} from "@/lib/team-actions";
import {
  departedAuthors,
  getTeamBySlug,
  isJoinRequest,
  listTeamDecisions,
  listTeamMembers,
  teamMcpUrl,
  weeklyTransferCount,
  type Team,
  type TeamMember,
} from "@/lib/teams";

export const dynamic = "force-dynamic";

const MCP_URL_ENV = "NEXT_PUBLIC_PITHUB_MCP_URL";
const RECENT_SIZE = 20;

interface PageProps {
  params: Promise<{ slug: string }>;
}

function Code({ children }: { children: string }) {
  return (
    <pre className="code">
      <code>{children}</code>
    </pre>
  );
}

function ConnectorCard({ team, url }: { team: Team; url: string }) {
  const mcpJson = JSON.stringify({ mcpServers: { [`pithub-${team.slug}`]: { type: "http", url } } }, null, 2);
  return (
    <div className="card">
      <h2 className="mb-2 text-[15px] font-semibold text-ink">팀 커넥터 주소</h2>
      <p className="muted mb-2 text-sm">
        팀 저장소의 <code className="text-ink">.mcp.json</code>에 넣어 커밋하면, 그 저장소에서 Claude Code를 쓰는 모든
        팀원의 세션이 이 팀으로 기록합니다. 로그인은 각자 GitHub로 한 번.
      </p>
      <Code>{mcpJson}</Code>
      <p className="muted mt-3 mb-2 text-sm">
        Codex는 저장소의 <code className="text-ink">.codex/config.toml</code>에:
      </p>
      <Code>{`[mcp_servers.pithub-${team.slug}]\nurl = "${url}"`}</Code>
      <p className="faint mt-3 text-xs">
        아직 구성원이 아닌 사람이 이 주소로 오면 자동으로 가입 요청이 되고, 소유자가 아래 구성원 칸에서 승인합니다.
        승인 전 기록은 본인만 보다가 승인 순간 팀 범위로 옮겨집니다. 저장소 밖(claude.ai)에서는 개인 커넥터를 쓰고
        프로젝트별 기본 범위로 팀을 고릅니다.
      </p>
    </div>
  );
}

function MemberRow({ member, team, isOwner, myId }: { member: TeamMember; team: Team; isOwner: boolean; myId: number }) {
  const pending = !member.accepted_at;
  const requested = isJoinRequest(member);
  return (
    <li className="flex items-center gap-3 py-2 text-sm">
      <span className={pending ? "muted" : "text-ink"}>{member.github_login}</span>
      {member.role === "owner" && <span className="faint text-xs">소유자</span>}
      {pending && <span className="badge badge-modify">{requested ? "가입 요청" : "초대 중"}</span>}
      {isOwner && requested && (
        <form action={approveMember} className="ml-auto">
          <input type="hidden" name="team_id" value={team.id} />
          <input type="hidden" name="slug" value={team.slug} />
          <input type="hidden" name="github_id" value={member.github_id} />
          <button className="btn btn-primary h-7 px-3 text-xs">승인</button>
        </form>
      )}
      {member.github_id === myId && member.role !== "owner" && (
        <form action={leaveTeam} className="ml-auto">
          <input type="hidden" name="team_id" value={team.id} />
          <button className="btn btn-ghost h-7 px-2 text-xs">나가기</button>
        </form>
      )}
      {isOwner && member.github_id !== myId && (
        <form action={removeMember} className={requested ? "" : "ml-auto"}>
          <input type="hidden" name="team_id" value={team.id} />
          <input type="hidden" name="slug" value={team.slug} />
          <input type="hidden" name="github_id" value={member.github_id} />
          <button className="btn btn-ghost h-7 px-2 text-xs">{requested ? "거절" : pending ? "초대 취소" : "내보내기"}</button>
        </form>
      )}
    </li>
  );
}

// 요청 시점의 시각 — react-hooks/purity 가 컴포넌트 본문의 Date 생성을 막으므로 밖에서 읽는다
function requestTime(): Date {
  return new Date();
}

/**
 * 팀 페이지 — 커넥터 주소, 팀 원칙, 최근 팀 결정, 구성원.
 * 팀원의 결정은 team_decisions 뷰로만 읽는다. 초대만 받은 사람에게는 팀 이름과 수락 안내만 보인다.
 */
export default async function TeamPage({ params }: PageProps) {
  const { slug } = await params;
  const user = await getUser();
  if (!user) redirect(`/?next=/t/${slug}`);
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");
  const team = await getTeamBySlug(supabase, slug);
  if (!team) notFound();

  const [members, decisions, transfers] = await Promise.all([
    listTeamMembers(supabase, team.id),
    listTeamDecisions(supabase, team.id),
    weeklyTransferCount(supabase, team.id, requestTime()),
  ]);
  const me = members.find((m) => m.github_id === account.github_id);
  if (!me?.accepted_at) redirect("/teams");
  const isOwner = me.role === "owner";
  const principles = decisions.filter((d) => d.tags.includes("principle"));
  const recent = decisions.filter((d) => !d.tags.includes("principle")).slice(0, RECENT_SIZE);
  const url = teamMcpUrl(process.env[MCP_URL_ENV] ?? "", slug);
  const departed = departedAuthors(decisions);

  return (
    <main>
      <Header signedIn handle={account.github_login} />
      <section className="page space-y-8">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{team.name}</h1>
          <span className="faint text-sm">/t/{team.slug}</span>
          <span className="faint text-sm">
            구성원 {members.filter((m) => m.accepted_at).length} · 팀 결정 {decisions.length}건
          </span>
          <span className="text-sm text-ink" title="동료의 AI가 다른 사람의 판단을 가져간 횟수 (최근 7일)">
            이번 주 건너간 판단 <b>{transfers}</b>건
          </span>
          <Link href={`/t/${slug}/agents`} className="link ml-auto text-sm">
            AGENTS.md 초안
          </Link>
        </div>

        <ConnectorCard team={team} url={url} />

        {principles.length > 0 && (
          <div>
            <h2 className="mb-3 text-[15px] font-semibold text-ink">팀 원칙</h2>
            <div className="space-y-3">
              {principles.map((d) => (
                <DecisionCard key={d.id} decision={d} href={`/d/${d.id}`} />
              ))}
            </div>
          </div>
        )}

        <div>
          <h2 className="mb-3 text-[15px] font-semibold text-ink">최근 팀 결정</h2>
          {recent.length === 0 ? (
            <div className="empty">
              아직 팀에 보인 결정이 없습니다. 팀 커넥터로 기록된 결정은 확인하거나 3일이 지나면 여기 나타납니다.
            </div>
          ) : (
            <div className="space-y-3">
              {recent.map((d) => (
                <DecisionCard key={d.id} decision={d} href={`/d/${d.id}`} />
              ))}
            </div>
          )}
        </div>

        {isOwner && (
          <form action={setJudgeConsent} className="card flex flex-wrap items-center gap-3">
            <input type="hidden" name="team_id" value={team.id} />
            <input type="hidden" name="slug" value={team.slug} />
            <input type="hidden" name="consent" value={team.external_judge_consent_at ? "off" : "on"} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">트윈 판정기 · JEV</p>
              <p className="muted text-xs">
                {team.external_judge_consent_at
                  ? "켜짐 — 트윈이 판정할 때 이 팀의 결정 요약(이름 없이)을 TypeSafe AI로 보냅니다."
                  : "꺼짐 — 트윈은 서버 안의 무료 판정기만 씁니다. 켜면 결정 요약(이름 없이)이 TypeSafe AI로 전송됩니다."}
              </p>
            </div>
            <button className={team.external_judge_consent_at ? "btn btn-secondary h-8 px-3" : "btn btn-primary h-8 px-3"}>
              {team.external_judge_consent_at ? "끄기" : "동의하고 켜기"}
            </button>
          </form>
        )}

        <div className="card">
          <h2 className="mb-2 text-[15px] font-semibold text-ink">구성원</h2>
          <ul className="divide-y divide-border">
            {members.map((m) => (
              <MemberRow key={m.github_id} member={m} team={team} isOwner={isOwner} myId={account.github_id} />
            ))}
          </ul>
          {isOwner && (
            <form action={inviteMember} className="mt-4 flex gap-2">
              <input type="hidden" name="team_id" value={team.id} />
              <input type="hidden" name="slug" value={team.slug} />
              <input name="login" placeholder="GitHub 아이디" className="input max-w-xs" required />
              <button className="btn btn-secondary shrink-0">초대</button>
            </form>
          )}
          {departed.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <p className="label mb-2">떠난 구성원 · 판단은 팀에 남아 후임에게 답합니다</p>
              <ul className="divide-y divide-border">
                {departed.map((d) => (
                  <li key={d.github_id} className="flex items-center gap-3 py-2 text-sm">
                    <span className="muted">{d.github_login}</span>
                    <span className="faint text-xs">판단 {d.count}건</span>
                    {isOwner && (
                      <form action={erasePersona} className="ml-auto">
                        <input type="hidden" name="team_id" value={team.id} />
                        <input type="hidden" name="slug" value={team.slug} />
                        <input type="hidden" name="github_id" value={d.github_id} />
                        <button className="btn btn-danger h-7 px-2 text-xs">페르소나 삭제</button>
                      </form>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="faint mt-3 text-xs">
            보통은 초대할 필요가 없습니다 — 팀 저장소에서 팀 주소로 처음 기록하는 사람이 여기 가입 요청으로 나타납니다.
            아이디로 초대하려면 그 사람이 pithub에 GitHub로 로그인한 적이 있어야 합니다. 팀에 보인 판단은 회사의 기록이라 사람이 나가거나
            계정을 지워도 남고, 소유자만 지웁니다. 본인만 보던 결정은 애초에 팀이 본 적이 없습니다.
          </p>
        </div>
      </section>
    </main>
  );
}
