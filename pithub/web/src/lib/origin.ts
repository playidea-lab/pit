/**
 * 사용자가 실제로 접속한 사이트 주소 — 컨테이너 안의 요청 주소(0.0.0.0:3000)가 아니라 프록시가 넘긴 헤더로
 */

import { headers } from "next/headers";

export async function siteOrigin(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "";
  const proto = h.get("x-forwarded-proto") ?? "https";
  return `${proto}://${host}`;
}
