/**
 * Supabase 클라이언트 설정
 */

import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/**
 * Supabase가 설정되어 있는지 확인
 */
export function isSupabaseConfigured(): boolean {
  return Boolean(supabaseUrl && supabaseAnonKey);
}

/**
 * Supabase 브라우저 클라이언트 생성
 * 환경변수가 없으면 null 반환
 */
export function createClient() {
  if (!supabaseUrl || !supabaseAnonKey) {
    return null;
  }

  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}

// 타입 정의
export interface Profile {
  id: string;
  github_username: string | null;
  github_avatar_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Repo {
  id: string;
  user_id: string;
  owner: string;
  name: string;
  default_branch: string;
  is_private: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  user_id: string;
  repo_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}
