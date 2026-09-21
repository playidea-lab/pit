import Link from "next/link";
import { getFeature } from "@/lib/api";
import Markdown from "@/components/Markdown";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
    featureId: string;
  }>;
}

export default async function FeaturePage({ params }: PageProps) {
  const { owner, repo, featureId } = await params;
  const feature = await getFeature(owner, repo, featureId);

  if (!feature) {
    return (
      <main className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <h1 className="text-3xl font-bold mb-4">Feature Not Found</h1>
          <Link
            href={`/${owner}/${repo}`}
            className="text-blue-400 hover:underline"
          >
            ← Back to project
          </Link>
        </div>
      </main>
    );
  }

  const progress = feature.checklist
    ? `${feature.checklist.filter((c) => c.done).length}/${feature.checklist.length}`
    : "0/0";

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-700 px-8 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-xl font-bold">
            <span className="text-blue-400">pit</span>hub
          </Link>
          <Link
            href={`/${owner}/${repo}`}
            className="text-gray-400 hover:text-white"
          >
            ← {owner}/{repo}
          </Link>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-8 py-8">
        {/* Feature Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-2">
            <span className="text-gray-500">{feature.id}</span>
            <StatusBadge status={feature.status} />
            <PriorityBadge priority={feature.priority} />
          </div>
          <h1 className="text-3xl font-bold mb-4">{feature.title}</h1>
          {feature.description && (
            <div className="text-gray-300">
              <Markdown content={feature.description} />
            </div>
          )}
        </div>

        {/* Progress */}
        <div className="bg-gray-800 rounded-lg p-6 mb-8">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg font-semibold">Progress</h2>
            <span className="text-2xl font-bold text-blue-400">{progress}</span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-3">
            <div
              className="bg-blue-500 h-3 rounded-full transition-all"
              style={{
                width: feature.checklist?.length
                  ? `${(feature.checklist.filter((c) => c.done).length / feature.checklist.length) * 100}%`
                  : "0%",
              }}
            />
          </div>
        </div>

        {/* Context */}
        {feature.context && (
          <section className="mb-8">
            <h2 className="text-xl font-bold mb-3">Context</h2>
            <div className="bg-gray-800 rounded-lg p-4">
              <Markdown content={feature.context} />
            </div>
          </section>
        )}

        {/* Requirements */}
        {feature.requirements && feature.requirements.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xl font-bold mb-3">Requirements</h2>
            <ul className="bg-gray-800 rounded-lg p-4 space-y-2">
              {feature.requirements.map((req, i) => (
                <li key={i} className="flex items-start gap-2 text-gray-300">
                  <span className="text-blue-400">•</span>
                  {req}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Checklist */}
        {feature.checklist && feature.checklist.length > 0 && (
          <section className="mb-8">
            <h2 className="text-xl font-bold mb-3">Checklist</h2>
            <ul className="bg-gray-800 rounded-lg p-4 space-y-3">
              {feature.checklist.map((item) => (
                <li
                  key={item.id}
                  className={`flex items-start gap-3 ${item.done ? "text-gray-500" : "text-gray-300"}`}
                >
                  <span
                    className={`mt-1 w-5 h-5 rounded border flex items-center justify-center text-sm ${
                      item.done
                        ? "bg-green-600 border-green-600"
                        : "border-gray-600"
                    }`}
                  >
                    {item.done && "✓"}
                  </span>
                  <div className="flex-1">
                    <span className={item.done ? "line-through" : ""}>
                      {item.label}
                    </span>
                    <span className="ml-2 text-xs text-gray-500">
                      [{item.type}]
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Metadata */}
        <section className="text-sm text-gray-500">
          {feature.created_at && (
            <div>Created: {new Date(feature.created_at).toLocaleString()}</div>
          )}
          {feature.updated_at && (
            <div>Updated: {new Date(feature.updated_at).toLocaleString()}</div>
          )}
        </section>
      </div>
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    planned: "bg-gray-600",
    in_progress: "bg-yellow-600",
    ready_for_merge: "bg-blue-600",
    merged: "bg-green-600",
    released: "bg-purple-600",
  };

  return (
    <span
      className={`px-2 py-1 rounded text-xs ${colors[status] || "bg-gray-600"}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    low: "bg-gray-700 text-gray-300",
    medium: "bg-blue-900 text-blue-300",
    high: "bg-orange-900 text-orange-300",
    critical: "bg-red-900 text-red-300",
  };

  return (
    <span
      className={`px-2 py-1 rounded text-xs ${colors[priority] || "bg-gray-700"}`}
    >
      {priority}
    </span>
  );
}
