/**
 * Repos Edge Function
 * GET /repos/:owner/:repo - repo 정보
 * GET /repos/:owner/:repo/summary - repo 요약 (features/decisions 개수)
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import {
  checkPitFolder,
  getPitConfig,
  listFeatureFiles,
  listDecisionFiles,
  getFeatureFile,
} from "../_shared/github.ts";

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // /repos/:owner/:repo 또는 /repos/:owner/:repo/summary
  if (pathParts.length < 3) {
    return errorResponse("Invalid path. Use /repos/:owner/:repo", 400);
  }

  const owner = pathParts[1];
  const repo = pathParts[2];
  const isSummary = pathParts[3] === "summary";

  // Authorization 헤더에서 토큰 추출 (선택적)
  const authHeader = req.headers.get("authorization");
  const token = authHeader?.replace("Bearer ", "");

  // branch 쿼리 파라미터
  const branch = url.searchParams.get("branch") || "main";

  try {
    // .pit/ 폴더 확인
    const hasPit = await checkPitFolder(owner, repo, branch, token);
    if (!hasPit) {
      return errorResponse(
        `.pit/ folder not found in ${owner}/${repo}`,
        404
      );
    }

    if (isSummary) {
      // Summary: config + features/decisions 개수
      const [config, features] = await Promise.all([
        getPitConfig(owner, repo, branch, token),
        listFeatureFiles(owner, repo, branch, token),
      ]);

      const decisions = await listDecisionFiles(owner, repo, branch, token);

      // Feature 상태별 집계
      const byStatus: Record<string, number> = {};
      for (const f of features) {
        const feature = await getFeatureFile(
          owner,
          repo,
          f.name.replace(".yaml", ""),
          branch,
          token
        );
        if (feature) {
          const status = (feature.status as string) || "unknown";
          byStatus[status] = (byStatus[status] || 0) + 1;
        }
      }

      return jsonResponse({
        owner,
        repo,
        branch,
        project: config || { id: repo, name: repo },
        features: {
          total: features.length,
          by_status: byStatus,
        },
        decisions: {
          total: decisions.length,
        },
      });
    } else {
      // 기본: config만
      const config = await getPitConfig(owner, repo, branch, token);

      return jsonResponse({
        owner,
        repo,
        branch,
        project: config || { id: repo, name: repo },
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
