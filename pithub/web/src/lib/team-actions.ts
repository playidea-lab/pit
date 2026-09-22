"use server";

/**
 * 팀에 대한 쓰기 — 팀·초대는 DB 함수(create_team · invite_to_team)로, 수락·탈퇴는 본인 행에만.
 * 전부 로그인한 사용자의 세션으로 실행되고 RLS와 함수가 권한을 집행한다.
 */

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getMyAccount } from "@/lib/decisions";
import { createServerSupabaseClient } from "@/lib/supabase-server";
import { TEAM_SLUG_PATTERN } from "@/lib/teams";

const MAX_NAME_CHARS = 60;

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function createTeam(form: FormData): Promise<void> {
  const slug = text(form, "slug").toLowerCase();
  const name = text(form, "name").slice(0, MAX_NAME_CHARS) || slug;
  if (!TEAM_SLUG_PATTERN.test(slug)) throw new Error("팀 주소는 소문자·숫자·하이픈 2~39자입니다.");

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.rpc("create_team", { team_slug: slug, team_name: name });
  if (error) throw new Error(`팀 만들기 실패: ${error.message}`);
  revalidatePath("/teams");
  redirect(`/t/${slug}`);
}

export async function inviteMember(form: FormData): Promise<void> {
  const teamId = text(form, "team_id");
  const slug = text(form, "slug");
  const login = text(form, "login").replace(/^@/, "");
  if (!login) return;

  const supabase = await createServerSupabaseClient();
  const { error } = await supabase.rpc("invite_to_team", { team: teamId, login });
  if (error) {
    const reason = error.code === "P0002" ? "그 GitHub 아이디로 pithub에 로그인한 적이 없습니다." : error.message;
    throw new Error(`초대 실패: ${reason}`);
  }
  revalidatePath(`/t/${slug}`);
}

export async function acceptInvite(form: FormData): Promise<void> {
  const teamId = text(form, "team_id");
  const slug = text(form, "slug");
  const supabase = await createServerSupabaseClient();
  const me = await getMyAccount(supabase);
  if (!me) throw new Error("로그인이 필요합니다.");

  const { error } = await supabase
    .from("team_members")
    .update({ accepted_at: new Date().toISOString() })
    .eq("team_id", teamId)
    .eq("github_id", me.github_id);
  if (error) throw new Error(`수락 실패: ${error.message}`);
  revalidatePath("/teams");
  redirect(`/t/${slug}`);
}

/** 초대 거절이자 팀 탈퇴 — 같은 행을 지운다. 팀 범위로 확정한 결정은 팀에 남는다. */
export async function leaveTeam(form: FormData): Promise<void> {
  const teamId = text(form, "team_id");
  const supabase = await createServerSupabaseClient();
  const me = await getMyAccount(supabase);
  if (!me) throw new Error("로그인이 필요합니다.");

  const { error } = await supabase.from("team_members").delete().eq("team_id", teamId).eq("github_id", me.github_id);
  if (error) throw new Error(`나가기 실패: ${error.message}`);
  revalidatePath("/teams");
  redirect("/teams");
}

export async function removeMember(form: FormData): Promise<void> {
  const teamId = text(form, "team_id");
  const slug = text(form, "slug");
  const githubId = Number(form.get("github_id"));
  const supabase = await createServerSupabaseClient();

  const { error } = await supabase.from("team_members").delete().eq("team_id", teamId).eq("github_id", githubId);
  if (error) throw new Error(`내보내기 실패: ${error.message}`);
  revalidatePath(`/t/${slug}`);
}
