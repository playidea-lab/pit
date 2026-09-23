import Link from "next/link";
import { redirect } from "next/navigation";

import Header from "@/components/Header";
import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";
import { acceptInvite, createTeam, leaveTeam } from "@/lib/team-actions";
import { listMyInvites, listMyTeams } from "@/lib/teams";

export const dynamic = "force-dynamic";

/** 내 팀과 초대장. 팀은 한 번 만들고, 초대는 본인이 수락한다. */
export default async function TeamsPage() {
  const user = await getUser();
  if (!user) redirect("/?next=/teams");
  const supabase = await createServerSupabaseClient();
  const account = await getMyAccount(supabase);
  if (!account) redirect("/");
  const [teams, invites] = await Promise.all([
    listMyTeams(supabase, account.github_id),
    listMyInvites(supabase, account.github_id),
  ]);

  return (
    <main>
      <Header signedIn handle={account.github_login} />
      <section className="page space-y-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">팀</h1>
          <p className="muted mt-1 text-sm">
            팀을 만들고 초대 링크를 팀 채널에 붙이세요. 링크를 누르고 로그인한 사람은 바로 팀원이 됩니다. 팀원이 AI와
            일하며 내린 판단은 3일 뒤 팀에 보이고, 서로의 AI가 그 판단을 먼저 찾아봅니다.
          </p>
        </div>

        {invites.length > 0 && (
          <div>
            <h2 className="mb-3 text-[15px] font-semibold text-ink">초대 · 가입 요청</h2>
            <div className="space-y-3">
              {invites.map(({ team, invited_by_login, requested_by_me }) => (
                <div key={team.id} className="card flex flex-wrap items-center gap-3">
                  <div>
                    <p className="text-ink">{team.name}</p>
                    <p className="faint text-xs">
                      /t/{team.slug}
                      {requested_by_me
                        ? " · 팀 주소로 기록해 가입 요청됨 · 소유자 승인 대기"
                        : invited_by_login && ` · ${invited_by_login} 님이 초대`}
                    </p>
                  </div>
                  {!requested_by_me && (
                    <form action={acceptInvite} className="ml-auto">
                      <input type="hidden" name="team_id" value={team.id} />
                      <input type="hidden" name="slug" value={team.slug} />
                      <button className="btn btn-primary h-8 px-3">수락</button>
                    </form>
                  )}
                  <form action={leaveTeam} className={requested_by_me ? "ml-auto" : ""}>
                    <input type="hidden" name="team_id" value={team.id} />
                    <button className="btn btn-ghost h-8 px-3">{requested_by_me ? "요청 취소" : "거절"}</button>
                  </form>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h2 className="mb-3 text-[15px] font-semibold text-ink">내 팀</h2>
          {teams.length === 0 ? (
            <div className="empty">아직 속한 팀이 없습니다.</div>
          ) : (
            <div className="space-y-3">
              {teams.map((team) => (
                <Link key={team.id} href={`/t/${team.slug}`} className="card-link flex items-center gap-3">
                  <span className="text-ink">{team.name}</span>
                  <span className="faint text-xs">/t/{team.slug}</span>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="mb-2 text-[15px] font-semibold text-ink">팀 만들기</h2>
          <p className="muted mb-3 text-sm">주소는 나중에 바꿀 수 없습니다. 소문자·숫자·하이픈.</p>
          <form action={createTeam} className="flex flex-wrap gap-2">
            <input name="slug" placeholder="주소 (예: pilab)" pattern="[a-z0-9][a-z0-9-]{1,38}" required className="input max-w-[12rem]" />
            <input name="name" placeholder="이름 (예: PI Lab)" className="input max-w-xs" />
            <button className="btn btn-primary shrink-0">만들기</button>
          </form>
        </div>
      </section>
    </main>
  );
}
