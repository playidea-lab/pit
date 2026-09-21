import Link from "next/link";
import {
  getRepoSummary,
  getFeatures,
  getDecisions,
  getReadMe,
  getIssues,
} from "@/lib/api";
import Markdown from "@/components/Markdown";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
  }>;
}

export default async function RepoPage({ params }: PageProps) {
  const { owner, repo } = await params;
  const [summary, features, decisions, readme, issues] = await Promise.all([
    getRepoSummary(owner, repo),
    getFeatures(owner, repo),
    getDecisions(owner, repo),
    getReadMe(owner, repo),
    getIssues(owner, repo, "open"),
  ]);

  if (!summary) {
    return (
      <main className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <h1 className="text-3xl font-bold mb-4">404</h1>
          <p className="text-gray-400 mb-8">
            <code className="bg-gray-700 px-2 py-1 rounded">.pit/</code> 폴더를
            찾을 수 없습니다
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
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">
            {summary.project.name || `${owner}/${repo}`}
          </h1>
          {summary.project.description && (
            <p className="text-gray-400">{summary.project.description}</p>
          )}
        </div>

        {/* Tab Navigation */}
        <nav className="flex gap-1 mb-8 border-b border-gray-700">
          <TabLink href={`/${owner}/${repo}`} active>
            <CodeIcon /> Overview
          </TabLink>
          <TabLink href={`/${owner}/${repo}/issues`}>
            <IssueIcon /> Issues
            {issues.length > 0 && (
              <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 rounded-full">
                {issues.length}
              </span>
            )}
          </TabLink>
        </nav>

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

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content - README */}
          <div className="lg:col-span-2">
            {/* README Section */}
            {readme && (
              <section className="mb-8">
                <div className="bg-gray-800 rounded-lg border border-gray-700">
                  <div className="px-4 py-3 border-b border-gray-700 flex items-center gap-2">
                    <BookIcon />
                    <span className="font-semibold">README.md</span>
                  </div>
                  <div className="p-4">
                    <Markdown content={readme} />
                  </div>
                </div>
              </section>
            )}

            {/* Features Section */}
            <section className="mb-8">
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <FeatureIcon /> Features
              </h2>
              {features.length === 0 ? (
                <p className="text-gray-500">No features yet</p>
              ) : (
                <div className="space-y-3">
                  {features.map((feature) => (
                    <Link
                      key={feature.id}
                      href={`/${owner}/${repo}/features/${feature.id}`}
                      className="block bg-gray-800 rounded-lg p-4 border border-gray-700 hover:border-blue-500 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-500">
                          {feature.id}
                        </span>
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
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <DecisionIcon /> Decisions
              </h2>
              {decisions.length === 0 ? (
                <p className="text-gray-500">No decisions yet</p>
              ) : (
                <div className="space-y-3">
                  {decisions.map((decision) => (
                    <Link
                      key={decision.id}
                      href={`/${owner}/${repo}/decisions/${decision.id}`}
                      className="block bg-gray-800 rounded-lg p-4 border border-gray-700 hover:border-purple-500 transition-colors"
                    >
                      <span className="text-sm text-gray-500">
                        {decision.id}
                      </span>
                      <h3 className="font-semibold mt-1">{decision.title}</h3>
                    </Link>
                  ))}
                </div>
              )}
            </section>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            {/* About */}
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-4">
              <h3 className="font-semibold mb-3">About</h3>
              <p className="text-gray-400 text-sm mb-4">
                {summary.project.description || "No description"}
              </p>
              <a
                href={`https://github.com/${owner}/${repo}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-gray-400 hover:text-blue-400"
              >
                <GitHubIcon /> {owner}/{repo}
              </a>
            </div>

            {/* Recent Issues */}
            {issues.length > 0 && (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                <h3 className="font-semibold mb-3 flex items-center justify-between">
                  Open Issues
                  <Link
                    href={`/${owner}/${repo}/issues`}
                    className="text-sm text-blue-400 font-normal"
                  >
                    View all →
                  </Link>
                </h3>
                <div className="space-y-3">
                  {issues.slice(0, 5).map((issue) => (
                    <Link
                      key={issue.number}
                      href={`/${owner}/${repo}/issues/${issue.number}`}
                      className="block text-sm hover:text-blue-400"
                    >
                      <div className="flex items-start gap-2">
                        <IssueOpenIcon className="mt-1 flex-shrink-0" />
                        <span className="line-clamp-2">{issue.title}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

function TabLink({
  href,
  active,
  children,
}: {
  href: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? "border-orange-500 text-white"
          : "border-transparent text-gray-400 hover:text-white hover:border-gray-600"
      }`}
    >
      {children}
    </Link>
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
    <span className={`${colors[priority] || "text-gray-400"}`}>{priority}</span>
  );
}

// Icons
function CodeIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
      />
    </svg>
  );
}

function IssueIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <circle cx="12" cy="12" r="10" strokeWidth={2} />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}

function IssueOpenIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`w-4 h-4 text-green-500 ${className || ""}`}
      fill="currentColor"
      viewBox="0 0 16 16"
    >
      <path d="M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" />
      <path
        fillRule="evenodd"
        d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z"
      />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg
      className="w-4 h-4"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
      />
    </svg>
  );
}

function FeatureIcon() {
  return (
    <svg
      className="w-5 h-5 text-blue-400"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
      />
    </svg>
  );
}

function DecisionIcon() {
  return (
    <svg
      className="w-5 h-5 text-purple-400"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
      <path
        fillRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
        clipRule="evenodd"
      />
    </svg>
  );
}
