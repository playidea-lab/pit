import Link from "next/link";
import { getRepoSummary, getFeatures, getDecisions } from "@/lib/api";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
  }>;
}

export default async function RepoPage({ params }: PageProps) {
  const { owner, repo } = await params;
  const [summary, features, decisions] = await Promise.all([
    getRepoSummary(owner, repo),
    getFeatures(owner, repo),
    getDecisions(owner, repo),
  ]);

  if (!summary) {
    return (
      <main className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <h1 className="text-3xl font-bold mb-4">404</h1>
          <p className="text-gray-400 mb-8">
            <code className="bg-gray-700 px-2 py-1 rounded">.pit/</code> 폴더를 찾을 수 없습니다
          </p>
          <p className="text-gray-500">
            {owner}/{repo} 저장소에 .pit/ 폴더가 있는지 확인해주세요.
          </p>
          <Link
            href="/"
            className="inline-block mt-8 px-6 py-2 bg-blue-500 rounded-lg hover:bg-blue-600"
          >
            홈으로
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-700 px-8 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-xl font-bold">
            <span className="text-blue-400">pit</span>hub
          </Link>
          <a
            href={`https://github.com/${owner}/${repo}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 hover:text-white"
          >
            View on GitHub →
          </a>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-8 py-8">
        {/* Project Info */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">
            {summary.project.name || `${owner}/${repo}`}
          </h1>
          {summary.project.description && (
            <p className="text-gray-400">{summary.project.description}</p>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Features"
            value={summary.features.total}
            color="blue"
          />
          <StatCard
            label="In Progress"
            value={summary.features.by_status?.in_progress || 0}
            color="yellow"
          />
          <StatCard
            label="Merged"
            value={summary.features.by_status?.merged || 0}
            color="green"
          />
          <StatCard
            label="Decisions"
            value={summary.decisions.total}
            color="purple"
          />
        </div>

        {/* Features Section */}
        <section className="mb-12">
          <h2 className="text-2xl font-bold mb-4">Features</h2>
          {features.length === 0 ? (
            <p className="text-gray-500">No features yet</p>
          ) : (
            <div className="grid gap-4">
              {features.map((feature) => (
                <Link
                  key={feature.id}
                  href={`/${owner}/${repo}/features/${feature.id}`}
                  className="block bg-gray-800 rounded-lg p-4 border border-gray-700 hover:border-blue-500 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-500">{feature.id}</span>
                    <StatusBadge status={feature.status} />
                  </div>
                  <h3 className="font-semibold mb-2">{feature.title}</h3>
                  <div className="flex items-center gap-4 text-sm text-gray-400">
                    <span>Progress: {feature.progress}</span>
                    <PriorityBadge priority={feature.priority} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* Decisions Section */}
        <section>
          <h2 className="text-2xl font-bold mb-4">Decisions</h2>
          {decisions.length === 0 ? (
            <p className="text-gray-500">No decisions yet</p>
          ) : (
            <div className="grid gap-4">
              {decisions.map((decision) => (
                <Link
                  key={decision.id}
                  href={`/${owner}/${repo}/decisions/${decision.id}`}
                  className="block bg-gray-800 rounded-lg p-4 border border-gray-700 hover:border-purple-500 transition-colors"
                >
                  <span className="text-sm text-gray-500">{decision.id}</span>
                  <h3 className="font-semibold mt-1">{decision.title}</h3>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: "blue" | "yellow" | "green" | "purple";
}) {
  const colorClasses = {
    blue: "border-blue-500 text-blue-400",
    yellow: "border-yellow-500 text-yellow-400",
    green: "border-green-500 text-green-400",
    purple: "border-purple-500 text-purple-400",
  };

  return (
    <div
      className={`bg-gray-800 rounded-lg p-4 border-l-4 ${colorClasses[color]}`}
    >
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-sm text-gray-400">{label}</div>
    </div>
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
    low: "text-gray-400",
    medium: "text-blue-400",
    high: "text-orange-400",
    critical: "text-red-400",
  };

  return (
    <span className={`${colors[priority] || "text-gray-400"}`}>
      {priority}
    </span>
  );
}
