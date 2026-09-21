import Link from "next/link";
import { getIssues } from "@/lib/api";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
  }>;
  searchParams: Promise<{
    state?: string;
  }>;
}

export default async function IssuesPage({ params, searchParams }: PageProps) {
  const { owner, repo } = await params;
  const { state = "open" } = await searchParams;
  const issues = await getIssues(
    owner,
    repo,
    state as "open" | "closed" | "all"
  );

  const openCount = state === "open" ? issues.length : 0;
  const closedCount = state === "closed" ? issues.length : 0;

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-700 px-8 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
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

      <div className="max-w-6xl mx-auto px-8 py-8">
        {/* Page Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <IssueIcon />
            Issues
          </h1>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-4 mb-6 border-b border-gray-700 pb-4">
          <Link
            href={`/${owner}/${repo}/issues?state=open`}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors ${
              state === "open"
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <IssueOpenIcon />
            Open
          </Link>
          <Link
            href={`/${owner}/${repo}/issues?state=closed`}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors ${
              state === "closed"
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            <IssueClosedIcon />
            Closed
          </Link>
          <a
            href={`https://github.com/${owner}/${repo}/issues`}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-sm text-gray-400 hover:text-blue-400"
          >
            View on GitHub →
          </a>
        </div>

        {/* Issues List */}
        {issues.length === 0 ? (
          <div className="text-center py-16">
            <IssueIcon className="w-12 h-12 mx-auto mb-4 text-gray-600" />
            <h2 className="text-xl font-semibold mb-2">No issues found</h2>
            <p className="text-gray-500">
              {state === "open"
                ? "There are no open issues in this repository."
                : "There are no closed issues in this repository."}
            </p>
          </div>
        ) : (
          <div className="border border-gray-700 rounded-lg overflow-hidden">
            {issues.map((issue, index) => (
              <Link
                key={issue.number}
                href={`/${owner}/${repo}/issues/${issue.number}`}
                className={`block p-4 hover:bg-gray-800 transition-colors ${
                  index !== issues.length - 1 ? "border-b border-gray-700" : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  {issue.state === "open" ? (
                    <IssueOpenIcon className="mt-1 flex-shrink-0" />
                  ) : (
                    <IssueClosedIcon className="mt-1 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold hover:text-blue-400">
                        {issue.title}
                      </span>
                      {issue.labels.map((label) => (
                        <span
                          key={label.name}
                          className="px-2 py-0.5 text-xs rounded-full"
                          style={{
                            backgroundColor: `#${label.color}20`,
                            color: `#${label.color}`,
                            border: `1px solid #${label.color}40`,
                          }}
                        >
                          {label.name}
                        </span>
                      ))}
                    </div>
                    <div className="text-sm text-gray-500 mt-1">
                      #{issue.number} opened{" "}
                      {formatDate(issue.created_at)} by {issue.user.login}
                      {issue.comments > 0 && (
                        <span className="ml-4">
                          <CommentIcon className="inline w-4 h-4 mr-1" />
                          {issue.comments}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      return `${diffMinutes} minutes ago`;
    }
    return `${diffHours} hours ago`;
  }
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
  return `${Math.floor(diffDays / 365)} years ago`;
}

// Icons
function IssueIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`w-5 h-5 ${className || ""}`}
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

function IssueClosedIcon({ className }: { className?: string }) {
  return (
    <svg
      className={`w-4 h-4 text-purple-500 ${className || ""}`}
      fill="currentColor"
      viewBox="0 0 16 16"
    >
      <path d="M11.28 6.78a.75.75 0 00-1.06-1.06L7.25 8.69 5.78 7.22a.75.75 0 00-1.06 1.06l2 2a.75.75 0 001.06 0l3.5-3.5z" />
      <path
        fillRule="evenodd"
        d="M16 8A8 8 0 110 8a8 8 0 0116 0zm-1.5 0a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z"
      />
    </svg>
  );
}

function CommentIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="currentColor"
      viewBox="0 0 16 16"
    >
      <path
        fillRule="evenodd"
        d="M2.75 2.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h2a.75.75 0 01.75.75v2.19l2.72-2.72a.75.75 0 01.53-.22h4.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25H2.75zM1 2.75C1 1.784 1.784 1 2.75 1h10.5c.966 0 1.75.784 1.75 1.75v7.5A1.75 1.75 0 0113.25 12H9.06l-2.53 2.53a.75.75 0 01-1.28-.53v-2H2.75A1.75 1.75 0 011 10.25v-7.5z"
      />
    </svg>
  );
}
