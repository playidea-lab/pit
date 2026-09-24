import Link from "next/link";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import CopyBox from "@/components/CopyBox";
import DecisionCard from "@/components/DecisionCard";
import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { listTopics } from "@/lib/graph";
import { siteOrigin } from "@/lib/origin";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import {
  approveMember,
  createInvite,
  erasePersona,
  inviteMember,
  leaveTeam,
  removeMember,
  revokeInvite,
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
const TOP_TOPICS = 12;
// team-actions.ts 의 createInvite 가 쓰는 한 번짜리 쿠키
const INVITE_COOKIE = "pithub_new_invite";

interface PageProps {
  params: Promise<{ slug: string }>;
}

function InviteCard({ team, inviteUrl }: { team: Team; inviteUrl: string | null }) {
  const live = team.invite_expires_at && new Date(team.invite_expires_at).getTime() > requestTime().getTime();
  return (
    <div className="card space-y-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">팀원 초대</h2>
        <p className="muted text-sm">
          링크를 팀 채널에 붙이세요. 누르고 회사 이메일이나 GitHub로 로그인하면 승인 없이 바로 팀원이 되고, 연결 안내로 넘어갑니다.
        </p>
      </div>
      {inviteUrl && <CopyBox value={inviteUrl} label="링크 복사" />}
      {inviteUrl && <p className="faint text-xs">이 링크는 지금 한 번만 보입니다. 잃어버리면 다시 만드세요.</p>}
      {!inviteUrl && live && (
        <p className="faint text-xs">
          살아 있는 링크가 있습니다 · {new Date(team.invite_expires_at as string).toLocaleDateString("ko-KR")}까지.
          원문은 만든 순간에만 보여서, 다시 보려면 새로 만들어야 합니다(이전 링크는 무효).
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <form action={createInvite}>
          <input type="hidden" name="team_id" value={team.id} />
          <input type="hidden" name="slug" value={team.slug} />
          <button className="btn btn-primary h-8 px-3">{live ? "새 링크 만들기" : "초대 링크 만들기"}</button>
        </form>
        {live && (
          <form action={revokeInvite}>
            <input type="hidden" name="team_id" value={team.id} />
            <input type="hidden" name="slug" value={team.slug} />
            <button className="btn btn-ghost h-8 px-3">링크 끄기</button>
          </form>
        )}
      </div>
      <p className="faint text-xs">링크는 7일 뒤 만료됩니다. 링크를 가진 사람은 누구나 들어올 수 있으니 팀 채널에만 두세요.</p>
    </div>
  );
}

function AddressCard({ team, url, teamUrl }: { team: Team; url: string; teamUrl: string }) {
  const mcpJson = JSON.stringify({ mcpServers: { [`pithub-${team.slug}`]: { type: "http", url: teamUrl } } }, null, 2);
  return (
    <div className="card space-y-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">연결 주소</h2>
        <p className="muted text-sm">
          팀원은 이 주소 하나를 쓰는 도구에 붙이면 됩니다. 방법은{" "}
          <Link href="/connect" className="link">
            연결하기
          </Link>
          에 도구별로 있습니다.
        </p>
      </div>
      <CopyBox value={url} label="주소 복사" />
      <details className="faint text-xs">
        <summary className="cursor-pointer">여러 팀에 속한 사람 · 저장소에 설정을 두고 싶을 때</summary>
        <div className="mt-2 space-y-2">
          <p>이 팀 전용 주소:</p>
          <CopyBox value={teamUrl} />
          <p>
            저장소 <code>.mcp.json</code>에 넣으면 그 저장소에서 여는 Claude Code가 자동으로 이 팀으로 붙습니다.
          </p>
          <pre className="code">
            <code>{mcpJson}</code>
          </pre>
        </div>
      </details>
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
  const topics = (await listTopics(supabase, team.id)).slice(0, TOP_TOPICS);
  const me = members.find((m) => m.github_id === account.github_id);
  if (!me?.accepted_at) redirect("/teams");
  const isOwner = me.role === "owner";
  const principles = decisions.filter((d) => d.tags.includes("principle"));
  const recent = decisions.filter((d) => !d.tags.includes("principle")).slice(0, RECENT_SIZE);
  const mcpUrl = process.env[MCP_URL_ENV] ?? "";
  const url = teamMcpUrl(mcpUrl, slug);
  const newToken = isOwner ? (await cookies()).get(INVITE_COOKIE)?.value : undefined;
  const inviteUrl = newToken ? `${await siteOrigin()}/join/${newToken}` : null;
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

        {isOwner && <InviteCard team={team} inviteUrl={inviteUrl} />}
        <AddressCard team={team} url={mcpUrl} teamUrl={url} />

        {topics.length > 0 && (
          <div>
            <div className="mb-3 flex items-baseline gap-3">
              <h2 className="text-[15px] font-semibold text-ink">주요 주제</h2>
              <Link href="/topics" className="link text-xs">
                전체
              </Link>
            </div>
            <div className="flex flex-wrap gap-2">
              {topics.map((t) => (
                <Link key={t.id} href={`/topic/${t.id}`} className="badge badge-choice hover:opacity-80">
                  {t.name} · {t.uses}
                </Link>
              ))}
            </div>
          </div>
        )}

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
              <input name="login" placeholder="pithub 아이디" className="input max-w-xs" required />
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
            보통은 위의 초대 링크면 충분합니다. 링크 없이 팀 주소로 먼저 기록한 사람은 여기 가입 요청으로 나타납니다.
            아이디로 초대하려면 그 사람이 pithub에 로그인한 적이 있어야 합니다(아이디는 설정 화면 맨 위). 팀에 보인 판단은 회사의 기록이라 사람이 나가거나
            계정을 지워도 남고, 소유자만 지웁니다. 본인만 보던 결정은 애초에 팀이 본 적이 없습니다.
          </p>
        </div>
      </section>
    </main>
  );
}
