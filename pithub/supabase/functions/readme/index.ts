/**
 * README Edge Function
 * GET /readme/:owner/:repo - README.md 내용 반환
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import { getReadMe, getGitHubToken } from "../_shared/github.ts";

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // /readme/:owner/:repo
  if (pathParts.length < 3) {
    return errorResponse("Invalid path. Use /readme/:owner/:repo", 400);
  }

  const owner = pathParts[1];
  const repo = pathParts[2];

  // 환경변수 또는 Authorization 헤더에서 토큰 추출
  const authHeader = req.headers.get("authorization");
  const userToken = authHeader?.replace("Bearer ", "");
  const token = getGitHubToken() || userToken;

  // branch 쿼리 파라미터
  const branch = url.searchParams.get("branch") || "main";

  try {
    const readme = await getReadMe(owner, repo, branch, token);

    if (!readme) {
      return errorResponse("README.md not found", 404);
    }

    return jsonResponse({ readme });
  } catch (error) {
    console.error("Error:", error);
    return errorResponse(
      error instanceof Error ? error.message : "Internal error",
      500
    );
  }
});
