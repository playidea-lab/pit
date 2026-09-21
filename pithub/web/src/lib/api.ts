/**
 * pithub API 클라이언트
 *
 * Supabase Edge Functions 또는 기존 FastAPI 백엔드 지원
 */

// Supabase Edge Functions URL (프로덕션) 또는 FastAPI (개발)
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const API_BASE = SUPABASE_URL
  ? `${SUPABASE_URL}/functions/v1`
  : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface Feature {
  id: string;
  title: string;
  status: string;
  priority: string;
  progress: string;
}

export interface FeatureDetail extends Feature {
  description?: string;
  context?: string;
  requirements?: string[];
  checklist?: {
    id: string;
    label: string;
    type: string;
    done: boolean;
  }[];
  created_at?: string;
  updated_at?: string;
  git_branch?: string;
}

export interface Decision {
  id: string;
  title: string;
  status?: string;
}

export interface DecisionDetail extends Decision {
  content: string;
  created_at?: string;
}

export interface GitHubIssue {
  number: number;
  title: string;
  body: string | null;
  state: "open" | "closed";
  created_at: string;
  updated_at: string;
  user: {
    login: string;
    avatar_url: string;
  };
  labels: Array<{
    name: string;
    color: string;
  }>;
  comments: number;
}

export interface ProjectConfig {
  id: string;
  name: string;
  description?: string;
  status?: string;
}

export interface RepoSummary {
  project: ProjectConfig;
  features: {
    total: number;
    by_status: Record<string, number>;
  };
  decisions: {
    total: number;
  };
}

/**
 * API 요청 헬퍼
 */
async function fetchAPI<T>(
  path: string,
  options: RequestInit = {}
): Promise<T | null> {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    // Supabase Edge Functions 사용 시 Authorization 헤더 추가
    if (SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
      headers["Authorization"] = `Bearer ${process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY}`;
    }

    const url = `${API_BASE}${path}`;
    console.log("[API] Fetching:", url);

    const res = await fetch(url, {
      ...options,
      headers,
    });

    console.log("[API] Response status:", res.status);

    if (!res.ok) {
      const errorText = await res.text();
      console.error("[API] Error:", errorText);
      return null;
    }
    return res.json();
  } catch (error) {
    console.error("[API] Fetch error:", error);
    return null;
  }
}

/**
 * Repo 요약 정보 조회
 */
export async function getRepoSummary(
  owner: string,
  repo: string
): Promise<RepoSummary | null> {
  // Supabase: /repos/{owner}/{repo}/summary
  // FastAPI: /api/repos/{owner}/{repo}/summary
  const path = SUPABASE_URL
    ? `/repos/${owner}/${repo}/summary`
    : `/repos/${owner}/${repo}/summary`;

  const data = await fetchAPI<{ owner: string; repo: string } & RepoSummary>(
    path
  );
  return data;
}

/**
 * Feature 목록 조회
 */
export async function getFeatures(
  owner: string,
  repo: string
): Promise<Feature[]> {
  const path = SUPABASE_URL
    ? `/features/${owner}/${repo}`
    : `/features/${owner}/${repo}`;

  const data = await fetchAPI<{ features: Feature[] }>(path);
  return data?.features || [];
}

/**
 * Feature 상세 조회
 */
export async function getFeature(
  owner: string,
  repo: string,
  featureId: string
): Promise<FeatureDetail | null> {
  const path = SUPABASE_URL
    ? `/features/${owner}/${repo}/${featureId}`
    : `/features/${owner}/${repo}/${featureId}`;

  const data = await fetchAPI<{ feature: FeatureDetail }>(path);
  return data?.feature || null;
}

/**
 * Decision 목록 조회
 */
export async function getDecisions(
  owner: string,
  repo: string
): Promise<Decision[]> {
  const path = SUPABASE_URL
    ? `/decisions/${owner}/${repo}`
    : `/decisions/${owner}/${repo}`;

  const data = await fetchAPI<{ decisions: Decision[] }>(path);
  return data?.decisions || [];
}

/**
 * Decision 상세 조회
 */
export async function getDecision(
  owner: string,
  repo: string,
  decisionId: string
): Promise<DecisionDetail | null> {
  const path = SUPABASE_URL
    ? `/decisions/${owner}/${repo}/${decisionId}`
    : `/decisions/${owner}/${repo}/${decisionId}`;

  const data = await fetchAPI<{ decision: DecisionDetail }>(path);
  return data?.decision || null;
}

/**
 * README.md 조회
 */
export async function getReadMe(
  owner: string,
  repo: string
): Promise<string | null> {
  const path = `/readme/${owner}/${repo}`;
  const data = await fetchAPI<{ readme: string }>(path);
  return data?.readme || null;
}

/**
 * Issues 목록 조회
 */
export async function getIssues(
  owner: string,
  repo: string,
  state: "open" | "closed" | "all" = "open"
): Promise<GitHubIssue[]> {
  const path = `/issues/${owner}/${repo}?state=${state}`;
  const data = await fetchAPI<{ issues: GitHubIssue[] }>(path);
  return data?.issues || [];
}

/**
 * Issue 상세 조회
 */
export async function getIssue(
  owner: string,
  repo: string,
  issueNumber: number
): Promise<GitHubIssue | null> {
  const path = `/issues/${owner}/${repo}/${issueNumber}`;
  const data = await fetchAPI<{ issue: GitHubIssue }>(path);
  return data?.issue || null;
}

/**
 * GitHub에 파일 커밋 (인증 필요)
 */
export async function commitToGitHub(params: {
  owner: string;
  repo: string;
  branch?: string;
  file_type: "feature" | "decision" | "config";
  file_id: string;
  content: Record<string, unknown>;
  message?: string;
  accessToken: string;
}): Promise<{ success: boolean; sha?: string; error?: string }> {
  if (!SUPABASE_URL) {
    return { success: false, error: "Supabase not configured" };
  }

  const { accessToken, ...body } = params;

  const res = await fetch(`${API_BASE}/github-commit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const error = await res.text();
    return { success: false, error };
  }

  return res.json();
}
