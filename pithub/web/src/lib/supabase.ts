/**
 * Supabase 브라우저 클라이언트
 *
 * 웹은 anon 키와 사용자 세션으로만 접근한다. 권한은 DB의 RLS가 집행한다.
 * service_role 키는 이 코드 어디에도 없어야 한다.
 */

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export function isSupabaseConfigured(): boolean {
  return Boolean(supabaseUrl && supabaseAnonKey);
}

let browserClient: SupabaseClient | null = null;

/** 모듈 싱글턴 — 렌더마다 새 클라이언트를 만들면 인증 구독이 매번 다시 붙는다 */
export function createClient(): SupabaseClient | null {
  if (!supabaseUrl || !supabaseAnonKey) {
    return null;
  }
  if (!browserClient) {
    browserClient = createBrowserClient(supabaseUrl, supabaseAnonKey);
  }
  return browserClient;
}
