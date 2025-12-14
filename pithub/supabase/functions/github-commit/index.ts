/**
 * GitHub Commit Edge Function
 * POST /github-commit - .pit/ 파일 생성/수정 후 커밋
 *
 * 기획자가 pithub 웹에서 채팅으로 Feature를 수정하면
 * 이 함수를 통해 GitHub에 직접 커밋됨
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import { commitFile, getFeatureFile, getDecisionFile } from "../_shared/github.ts";

interface CommitRequest {
  owner: string;
  repo: string;
  branch?: string;
  file_type: "feature" | "decision" | "config";
  file_id: string;
  content: Record<string, unknown>;
  message?: string;
}

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  if (req.method !== "POST") {
    return errorResponse("Method not allowed", 405);
  }

  // Authorization 필수
  const authHeader = req.headers.get("authorization");
  if (!authHeader) {
    return errorResponse("Authorization required", 401);
  }

  try {
    // Supabase 클라이언트로 사용자 확인
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseKey, {
      global: { headers: { Authorization: authHeader } },
    });

    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return errorResponse("Invalid token", 401);
    }

    // 사용자의 GitHub 토큰 가져오기
    const { data: profile } = await supabase
      .from("profiles")
      .select("github_access_token")
      .eq("id", user.id)
      .single();

    if (!profile?.github_access_token) {
      return errorResponse("GitHub token not found. Please re-login.", 401);
    }

    const githubToken = profile.github_access_token;

    // 요청 바디 파싱
    const body = (await req.json()) as CommitRequest;
    const {
      owner,
      repo,
      branch = "pithub/draft",
      file_type,
      file_id,
      content,
      message,
    } = body;

    if (!owner || !repo || !file_type || !file_id || !content) {
      return errorResponse(
        "Missing required fields: owner, repo, file_type, file_id, content",
        400
      );
    }

    // 파일 경로 결정
    let filePath: string;
    let fileContent: string;
    let existingSha: string | undefined;

    switch (file_type) {
      case "feature": {
        filePath = `.pit/features/${file_id}.yaml`;
        // 기존 파일 SHA 확인
        const existing = await getFeatureFile(owner, repo, file_id, branch, githubToken);
        existingSha = existing?._sha as string | undefined;
        // YAML로 변환
        fileContent = objectToYaml(content);
        break;
      }
      case "decision": {
        filePath = `.pit/decisions/${file_id}.md`;
        const existing = await getDecisionFile(owner, repo, file_id, branch, githubToken);
        existingSha = existing?._sha as string | undefined;
        // Markdown + frontmatter로 변환
        const { frontmatter, body: mdBody } = separateContent(content);
        fileContent = `---\n${objectToYaml(frontmatter)}---\n\n${mdBody}`;
        break;
      }
      case "config": {
        filePath = `.pit/config.yaml`;
        fileContent = objectToYaml(content);
        break;
      }
      default:
        return errorResponse(`Invalid file_type: ${file_type}`, 400);
    }

    // 커밋 메시지 생성
    const commitMessage =
      message ||
      `[pithub] Update ${file_type} ${file_id}\n\nModified via pithub web`;

    // GitHub에 커밋
    const result = await commitFile(
      owner,
      repo,
      filePath,
      fileContent,
      commitMessage,
      branch,
      existingSha,
      githubToken
    );

    if (!result.success) {
      return errorResponse(result.error || "Commit failed", 500);
    }

    return jsonResponse({
      success: true,
      sha: result.sha,
      path: filePath,
      branch,
    });
  } catch (error) {
    console.error("Error:", error);
    return errorResponse(
      error instanceof Error ? error.message : "Internal error",
      500
    );
  }
});

/**
 * 객체를 YAML 문자열로 변환 (간단한 구현)
 */
function objectToYaml(obj: Record<string, unknown>, indent = 0): string {
  const spaces = "  ".repeat(indent);
  let result = "";

  for (const [key, value] of Object.entries(obj)) {
    if (key.startsWith("_")) continue; // _sha 같은 내부 필드 스킵

    if (value === null || value === undefined) {
      result += `${spaces}${key}: null\n`;
    } else if (typeof value === "boolean") {
      result += `${spaces}${key}: ${value}\n`;
    } else if (typeof value === "number") {
      result += `${spaces}${key}: ${value}\n`;
    } else if (typeof value === "string") {
      // 멀티라인 문자열 처리
      if (value.includes("\n")) {
        result += `${spaces}${key}: |\n`;
        for (const line of value.split("\n")) {
          result += `${spaces}  ${line}\n`;
        }
      } else if (value.length > 80) {
        result += `${spaces}${key}: >\n${spaces}  ${value}\n`;
      } else {
        result += `${spaces}${key}: ${value}\n`;
      }
    } else if (Array.isArray(value)) {
      result += `${spaces}${key}:\n`;
      for (const item of value) {
        if (typeof item === "object" && item !== null) {
          result += `${spaces}  - ${objectToYaml(item as Record<string, unknown>, indent + 2).trim().replace(/\n/g, `\n${spaces}    `)}\n`;
        } else {
          result += `${spaces}  - ${item}\n`;
        }
      }
    } else if (typeof value === "object") {
      result += `${spaces}${key}:\n${objectToYaml(value as Record<string, unknown>, indent + 1)}`;
    }
  }

  return result;
}

/**
 * content 필드를 frontmatter와 body로 분리
 */
function separateContent(obj: Record<string, unknown>): {
  frontmatter: Record<string, unknown>;
  body: string;
} {
  const { content, ...frontmatter } = obj;
  return {
    frontmatter,
    body: (content as string) || "",
  };
}
