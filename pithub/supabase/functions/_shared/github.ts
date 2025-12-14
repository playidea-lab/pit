/**
 * GitHub API 헬퍼 함수들 (Deno 런타임용)
 */

const GITHUB_API_BASE = "https://api.github.com";

/**
 * 환경변수에서 GitHub 토큰 가져오기
 */
export function getGitHubToken(): string | undefined {
  return Deno.env.get("GITHUB_TOKEN");
}

export interface GitHubFile {
  name: string;
  path: string;
  sha: string;
  type: "file" | "dir";
  content?: string;
  encoding?: string;
}

export interface GitHubContent {
  sha: string;
  content: string;
  encoding: string;
}

/**
 * GitHub API 요청
 */
async function githubFetch(
  path: string,
  token?: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github.v3+json",
    "User-Agent": "pithub",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return fetch(`${GITHUB_API_BASE}${path}`, {
    ...options,
    headers,
  });
}

/**
 * .pit/ 폴더 존재 여부 확인
 */
export async function checkPitFolder(
  owner: string,
  repo: string,
  branch = "main",
  token?: string
): Promise<boolean> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit?ref=${branch}`,
    token
  );
  return res.ok;
}

/**
 * .pit/config.yaml 읽기
 */
export async function getPitConfig(
  owner: string,
  repo: string,
  branch = "main",
  token?: string
): Promise<Record<string, unknown> | null> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit/config.yaml?ref=${branch}`,
    token
  );

  if (!res.ok) return null;

  const data = (await res.json()) as GitHubContent;
  const content = atob(data.content.replace(/\n/g, ""));

  // YAML 파싱 (간단한 구현)
  return parseYaml(content);
}

/**
 * .pit/features/ 폴더의 파일 목록
 */
export async function listFeatureFiles(
  owner: string,
  repo: string,
  branch = "main",
  token?: string
): Promise<GitHubFile[]> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit/features?ref=${branch}`,
    token
  );

  if (!res.ok) return [];

  const files = (await res.json()) as GitHubFile[];
  return files.filter(
    (f) => f.type === "file" && f.name.endsWith(".yaml")
  );
}

/**
 * 특정 Feature 파일 읽기
 */
export async function getFeatureFile(
  owner: string,
  repo: string,
  featureId: string,
  branch = "main",
  token?: string
): Promise<Record<string, unknown> | null> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit/features/${featureId}.yaml?ref=${branch}`,
    token
  );

  if (!res.ok) return null;

  const data = (await res.json()) as GitHubContent;
  const content = atob(data.content.replace(/\n/g, ""));

  return { ...parseYaml(content), _sha: data.sha };
}

/**
 * .pit/decisions/ 폴더의 파일 목록
 */
export async function listDecisionFiles(
  owner: string,
  repo: string,
  branch = "main",
  token?: string
): Promise<GitHubFile[]> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit/decisions?ref=${branch}`,
    token
  );

  if (!res.ok) return [];

  const files = (await res.json()) as GitHubFile[];
  return files.filter(
    (f) => f.type === "file" && f.name.endsWith(".md")
  );
}

/**
 * 특정 Decision 파일 읽기
 */
export async function getDecisionFile(
  owner: string,
  repo: string,
  decisionId: string,
  branch = "main",
  token?: string
): Promise<Record<string, unknown> | null> {
  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/.pit/decisions/${decisionId}.md?ref=${branch}`,
    token
  );

  if (!res.ok) return null;

  const data = (await res.json()) as GitHubContent;
  const content = atob(data.content.replace(/\n/g, ""));

  // Frontmatter 파싱
  const { frontmatter, body } = parseFrontmatter(content);

  return { ...frontmatter, content: body, _sha: data.sha };
}

/**
 * GitHub에 파일 생성/수정 (커밋)
 */
export async function commitFile(
  owner: string,
  repo: string,
  path: string,
  content: string,
  message: string,
  branch: string,
  sha?: string, // 수정 시 필요
  token?: string
): Promise<{ success: boolean; sha?: string; error?: string }> {
  if (!token) {
    return { success: false, error: "Authentication required" };
  }

  const body: Record<string, unknown> = {
    message,
    content: btoa(content),
    branch,
  };

  if (sha) {
    body.sha = sha;
  }

  const res = await githubFetch(
    `/repos/${owner}/${repo}/contents/${path}`,
    token,
    {
      method: "PUT",
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    const error = await res.text();
    return { success: false, error };
  }

  const data = await res.json();
  return { success: true, sha: data.content?.sha };
}

/**
 * 간단한 YAML 파서 (의존성 없이)
 */
function parseYaml(content: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = content.split("\n");
  let currentKey = "";
  let currentArray: string[] | null = null;

  for (const line of lines) {
    const trimmed = line.trim();

    // 빈 줄이나 주석 스킵
    if (!trimmed || trimmed.startsWith("#")) continue;

    // 배열 아이템
    if (trimmed.startsWith("- ")) {
      if (currentArray) {
        const value = trimmed.slice(2).trim();
        // 객체 형태의 배열 아이템인지 확인
        if (value.includes(":")) {
          const obj: Record<string, unknown> = {};
          const parts = value.split(":");
          obj[parts[0].trim()] = parseValue(parts.slice(1).join(":").trim());
          currentArray.push(obj as unknown as string);
        } else {
          currentArray.push(parseValue(value) as string);
        }
      }
      continue;
    }

    // key: value 형태
    const colonIndex = trimmed.indexOf(":");
    if (colonIndex > 0) {
      // 이전 배열 저장
      if (currentArray && currentKey) {
        result[currentKey] = currentArray;
        currentArray = null;
      }

      const key = trimmed.slice(0, colonIndex).trim();
      const value = trimmed.slice(colonIndex + 1).trim();

      if (value === "" || value === ">") {
        // 다음 줄이 배열이거나 멀티라인
        currentKey = key;
        if (trimmed.endsWith(">")) {
          result[key] = ""; // 멀티라인 문자열 (간단 처리)
        } else {
          currentArray = [];
        }
      } else {
        result[key] = parseValue(value);
        currentKey = key;
      }
    }
  }

  // 마지막 배열 저장
  if (currentArray && currentKey) {
    result[currentKey] = currentArray;
  }

  return result;
}

/**
 * YAML 값 파싱
 */
function parseValue(value: string): unknown {
  // 따옴표 제거
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }

  // boolean
  if (value === "true") return true;
  if (value === "false") return false;

  // null
  if (value === "null" || value === "~") return null;

  // number
  const num = Number(value);
  if (!isNaN(num)) return num;

  return value;
}

/**
 * Markdown frontmatter 파싱
 */
function parseFrontmatter(content: string): {
  frontmatter: Record<string, unknown>;
  body: string;
} {
  const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);

  if (!match) {
    return { frontmatter: {}, body: content };
  }

  return {
    frontmatter: parseYaml(match[1]),
    body: match[2].trim(),
  };
}
