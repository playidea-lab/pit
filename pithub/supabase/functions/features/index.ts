/**
 * Features Edge Function
 * GET /features/:owner/:repo - feature 목록
 * GET /features/:owner/:repo/:featureId - feature 상세
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import {
  handleCors,
  jsonResponse,
  errorResponse,
} from "../_shared/cors.ts";
import {
  listFeatureFiles,
  getFeatureFile,
  getGitHubToken,
} from "../_shared/github.ts";

interface Feature {
  id: string;
  title: string;
  status: string;
  priority: string;
  progress: string;
}

interface FeatureDetail extends Feature {
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

serve(async (req: Request) => {
  // CORS preflight
  const corsRes = handleCors(req);
  if (corsRes) return corsRes;

  const url = new URL(req.url);
  const pathParts = url.pathname.split("/").filter(Boolean);

  // /features/:owner/:repo 또는 /features/:owner/:repo/:featureId
  if (pathParts.length < 3) {
    return errorResponse(
      "Invalid path. Use /features/:owner/:repo or /features/:owner/:repo/:featureId",
      400
    );
  }

  const owner = pathParts[1];
  const repo = pathParts[2];
  const featureId = pathParts[3];

  // 환경변수 또는 Authorization 헤더에서 토큰 추출
  const authHeader = req.headers.get("authorization");
  const userToken = authHeader?.replace("Bearer ", "");
  const token = getGitHubToken() || userToken;

  // branch 쿼리 파라미터
  const branch = url.searchParams.get("branch") || "main";

  try {
    if (featureId) {
      // 특정 Feature 상세
      const feature = await getFeatureFile(owner, repo, featureId, branch, token);

      if (!feature) {
        return errorResponse(`Feature ${featureId} not found`, 404);
      }

      // checklist에서 progress 계산
      const checklist = feature.checklist as FeatureDetail["checklist"];
      const progress = checklist
        ? `${checklist.filter((c) => c.done).length}/${checklist.length}`
        : "0/0";

      const detail: FeatureDetail = {
        id: (feature.id as string) || featureId,
        title: (feature.title as string) || "",
        status: (feature.status as string) || "planned",
        priority: (feature.priority as string) || "medium",
        progress,
        description: feature.description as string,
        context: feature.context as string,
        requirements: feature.requirements as string[],
        checklist,
        created_at: feature.created_at as string,
        updated_at: feature.updated_at as string,
        git_branch: feature.git_branch as string,
      };

      return jsonResponse({ feature: detail });
    } else {
      // Feature 목록
      const files = await listFeatureFiles(owner, repo, branch, token);

      const features: Feature[] = [];
      for (const file of files) {
        const id = file.name.replace(".yaml", "");
        const feature = await getFeatureFile(owner, repo, id, branch, token);

        if (feature) {
          const checklist = feature.checklist as FeatureDetail["checklist"];
          const progress = checklist
            ? `${checklist.filter((c) => c.done).length}/${checklist.length}`
            : "0/0";

          features.push({
            id: (feature.id as string) || id,
            title: (feature.title as string) || "",
            status: (feature.status as string) || "planned",
            priority: (feature.priority as string) || "medium",
            progress,
          });
        }
      }

      return jsonResponse({ features });
    }
  } catch (error) {
    console.error("Error:", error);
    return errorResponse(
      error instanceof Error ? error.message : "Internal error",
      500
    );
  }
});
