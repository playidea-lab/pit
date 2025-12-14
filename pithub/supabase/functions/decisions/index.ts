/**
 * Decisions Edge Function
 * GET /decisions/:owner/:repo - decision 목록
 * GET /decisions/:owner/:repo/:decisionId - decision 상세
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import {
  listDecisionFiles,
  getDecisionFile,
  getGitHubToken,
} from "../_shared/github.ts";

interface Decision {
  id: string;
  title: string;
  status?: string;
}

interface DecisionDetail extends Decision {
  content: string;
  created_at?: string;
}

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // /decisions/:owner/:repo 또는 /decisions/:owner/:repo/:decisionId
  if (pathParts.length < 3) {
    return errorResponse(
      "Invalid path. Use /decisions/:owner/:repo or /decisions/:owner/:repo/:decisionId",
      400
    );
  }

  const owner = pathParts[1];
  const repo = pathParts[2];
  const decisionId = pathParts[3];

  // 환경변수 또는 Authorization 헤더에서 토큰 추출
  const authHeader = req.headers.get("authorization");
  const userToken = authHeader?.replace("Bearer ", "");
  const token = getGitHubToken() || userToken;

  // branch 쿼리 파라미터
  const branch = url.searchParams.get("branch") || "main";

  try {
    if (decisionId) {
      // 특정 Decision 상세
      const decision = await getDecisionFile(
        owner,
        repo,
        decisionId,
        branch,
        token
      );

      if (!decision) {
        return errorResponse(`Decision ${decisionId} not found`, 404);
      }

      const detail: DecisionDetail = {
        id: (decision.id as string) || decisionId,
        title: (decision.title as string) || "",
        status: decision.status as string,
        content: (decision.content as string) || "",
        created_at: decision.created_at as string,
      };

      return jsonResponse({ decision: detail });
    } else {
      // Decision 목록
      const files = await listDecisionFiles(owner, repo, branch, token);

      const decisions: Decision[] = [];
      for (const file of files) {
        const id = file.name.replace(".md", "");
        const decision = await getDecisionFile(owner, repo, id, branch, token);

        if (decision) {
          decisions.push({
            id: (decision.id as string) || id,
            title: (decision.title as string) || "",
            status: decision.status as string,
          });
        }
      }

      return jsonResponse({ decisions });
    }
  } catch (error) {
    console.error("Error:", error);
    return errorResponse(
      error instanceof Error ? error.message : "Internal error",
      500
    );
  }
});
