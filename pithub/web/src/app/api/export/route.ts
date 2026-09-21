/**
 * 내 결정 전체를 JSON 파일로 내려준다 (초안·확정·버린 것 모두, 출처 열 포함)
 */

import { NextResponse } from "next/server";

import { createServerSupabaseClient, getUser } from "@/lib/supabase-server";

const EXPORT_LIMIT = 10000;

export async function GET() {
  const user = await getUser();
  if (!user) {
    return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }

  const supabase = await createServerSupabaseClient();
  const [decisions, reviews] = await Promise.all([
    supabase.from("decisions").select("*").order("decided_at").limit(EXPORT_LIMIT),
    supabase.from("review_events").select("*").order("created_at").limit(EXPORT_LIMIT),
  ]);
  if (decisions.error || reviews.error) {
    return NextResponse.json({ error: "내보내기에 실패했습니다." }, { status: 500 });
  }

  const payload = {
    exported_at: new Date().toISOString(),
    decisions: decisions.data,
    review_events: reviews.data,
  };
  const stamp = payload.exported_at.slice(0, 10);
  return new NextResponse(JSON.stringify(payload, null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "content-disposition": `attachment; filename="pithub-export-${stamp}.json"`,
    },
  });
}
