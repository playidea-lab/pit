/**
 * Issues Edge Function
 * GET /issues/:owner/:repo - Issue 목록
 * GET /issues/:owner/:repo/:issueNumber - Issue 상세
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import {
  listIssues,
  getIssue,
  getGitHubToken,
  GitHubIssue,
} from "../_shared/github.ts";

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // /issues/:owner/:repo 또는 /issues/:owner/:repo/:issueNumber
  if (pathParts.length < 3) {
    return errorResponse(
      "Invalid path. Use /issues/:owner/:repo or /issues/:owner/:repo/:issueNumber",
      400
    );
  }

  const owner = pathParts[1];
  const repo = pathParts[2];
  const issueNumber = pathParts[3] ? parseInt(pathParts[3], 10) : undefined;

  // 환경변수 또는 Authorization 헤더에서 토큰 추출
  const authHeader = req.headers.get("authorization");
  const userToken = authHeader?.replace("Bearer ", "");
  const token = getGitHubToken() || userToken;

  // 쿼리 파라미터
  const state = (url.searchParams.get("state") || "open") as
    | "open"
    | "closed"
    | "all";
  const page = parseInt(url.searchParams.get("page") || "1", 10);
  const perPage = parseInt(url.searchParams.get("per_page") || "30", 10);

  try {
    if (issueNumber) {
      // 특정 Issue 상세
      const issue = await getIssue(owner, repo, issueNumber, token);

      if (!issue) {
        return errorResponse(`Issue #${issueNumber} not found`, 404);
      }

      return jsonResponse({ issue });
    } else {
      // Issue 목록
      const issues = await listIssues(owner, repo, state, token, page, perPage);

      return jsonResponse({
        issues,
        pagination: {
          page,
          per_page: perPage,
          state,
        },
      });
    }
  } catch (error) {
    console.error("Error:", error);
    return errorResponse(
      error instanceof Error ? error.message : "Internal error",
      500
    );
  }
});
