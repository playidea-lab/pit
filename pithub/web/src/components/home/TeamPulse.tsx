import type { SupabaseClient } from "@supabase/supabase-js";
import Link from "next/link";

import DecisionCard from "@/components/DecisionCard";
import { listTopics } from "@/lib/graph";
import { listTeamDecisions, weeklyTransferCount, type Team } from "@/lib/teams";

const DAYS_IN_WEEK = 7;
const MS_PER_DAY = 86_400_000;
const TOP_TOPICS = 6;
const RECENT = 3;

function Metric({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div title={hint}>
      <p className="label mb-0.5">{label}</p>
      <p className="text-xl font-semibold text-ink">{value}</p>
    </div>
  );
}

function requestTime(): Date {
  return new Date();
}

/** 팀 현황 — 이번 주에 팀에 쌓이고 건너간 판단, 많이 다룬 주제, 최근 판단 */
export default async function TeamPulse({ supabase, team }: { supabase: SupabaseClient; team: Team }) {
  const now = requestTime();
  const [decisions, transfers, topics] = await Promise.all([
    listTeamDecisions(supabase, team.id),
    weeklyTransferCount(supabase, team.id, now),
    listTopics(supabase, team.id),
  ]);
  const weekAgo = now.getTime() - DAYS_IN_WEEK * MS_PER_DAY;
  const thisWeek = decisions.filter((d) => new Date(d.decided_at).getTime() >= weekAgo).length;
  const principles = decisions.filter((d) => d.tags.includes("principle")).length;
  const authors = new Set(decisions.map((d) => d.owner_github_id)).size;

  return (
    <div className="card space-y-5">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[15px] font-semibold text-ink">{team.name}</h2>
        <Link href={`/t/${team.slug}`} className="link ml-auto text-xs">
          팀 페이지
        </Link>
      </div>
      <div className="flex flex-wrap gap-x-10 gap-y-3">
        <Metric label="이번 주 팀 판단" value={thisWeek} hint="최근 7일 팀에 보이게 된 판단" />
        <Metric label="건너간 판단" value={transfers} hint="최근 7일 동료의 AI가 다른 사람의 판단을 가져간 횟수" />
        <Metric label="원칙" value={principles} hint="팀에 보인 원칙" />
        <Metric label="판단을 남긴 사람" value={authors} hint="팀에 보인 판단의 작성자 수" />
      </div>
      {topics.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {topics.slice(0, TOP_TOPICS).map((t) => (
            <Link key={t.id} href={`/topic/${t.id}`} className="badge badge-choice hover:opacity-80">
              {t.name} · {t.uses}
            </Link>
          ))}
        </div>
      )}
      {decisions.length === 0 ? (
        <p className="muted text-sm">아직 팀에 보인 판단이 없습니다. 기록은 3일 뒤 여기 나타납니다.</p>
      ) : (
        <div className="space-y-3">
          {decisions.slice(0, RECENT).map((d) => (
            <DecisionCard key={d.id} decision={d} href={`/d/${d.id}`} />
          ))}
        </div>
      )}
    </div>
  );
}
