import Link from "next/link";
import { getIssue } from "@/lib/api";
import Markdown from "@/components/Markdown";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
    issueNumber: string;
  }>;
}

export default async function IssuePage({ params }: PageProps) {
  const { owner, repo, issueNumber } = await params;
  const issue = await getIssue(owner, repo, parseInt(issueNumber, 10));

  if (!issue) {
    return (
      <main className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <h1 className="text-3xl font-bold mb-4">Issue Not Found</h1>
          <Link
            href={`/${owner}/${repo}/issues`}
            className="text-blue-400 hover:underline"
          >
            ← Back to issues
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-700 px-8 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-xl font-bold">
            <span className="text-blue-400">pit</span>hub
          </Link>
          <Link
            href={`/${owner}/${repo}/issues`}
            className="text-gray-400 hover:text-white"
          >
            ← {owner}/{repo}/issues
          </Link>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-8 py-8">
        {/* Issue Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-3">
            {issue.title}{" "}
            <span className="text-gray-500 font-normal">#{issue.number}</span>
          </h1>

          <div className="flex items-center gap-3 flex-wrap">
            {/* State Badge */}
            {issue.state === "open" ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-green-900 text-green-300">
                <IssueOpenIcon />
                Open
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-purple-900 text-purple-300">
                <IssueClosedIcon />
                Closed
              </span>
            )}

            {/* Meta Info */}
            <span className="text-gray-400 text-sm">
              <a
                href={`https://github.com/${issue.user.login}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-gray-300 hover:text-blue-400"
              >
                {issue.user.login}
              </a>{" "}
              opened this issue on {formatDate(issue.created_at)}
              {issue.comments > 0 && ` · ${issue.comments} comments`}
            </span>
          </div>
        </div>

        {/* Labels */}
        {issue.labels.length > 0 && (
          <div className="flex items-center gap-2 mb-6 flex-wrap">
            {issue.labels.map((label) => (
              <span
                key={label.name}
                className="px-2.5 py-1 text-xs font-medium rounded-full"
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
        )}

        {/* Issue Body */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {/* Author Header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-850 border-b border-gray-700">
            <img
              src={issue.user.avatar_url}
              alt={issue.user.login}
              className="w-8 h-8 rounded-full"
            />
            <div>
              <a
                href={`https://github.com/${issue.user.login}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-gray-300 hover:text-blue-400"
              >
                {issue.user.login}
              </a>
              <span className="text-gray-500 text-sm ml-2">
                commented on {formatDate(issue.created_at)}
              </span>
            </div>
          </div>

          {/* Body Content */}
          <div className="p-4">
            {issue.body ? (
              <Markdown content={issue.body} />
            ) : (
              <p className="text-gray-500 italic">No description provided.</p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="mt-6 flex items-center justify-between">
          <Link
            href={`/${owner}/${repo}/issues`}
            className="text-gray-400 hover:text-white"
          >
            ← Back to issues
          </Link>
          <a
            href={`https://github.com/${owner}/${repo}/issues/${issue.number}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition-colors"
          >
            <GitHubIcon />
            View on GitHub
          </a>
        </div>

        {/* Comments Notice */}
        {issue.comments > 0 && (
          <div className="mt-8 p-4 bg-gray-800 rounded-lg border border-gray-700 text-center">
            <p className="text-gray-400">
              This issue has{" "}
              <span className="font-semibold text-white">
                {issue.comments} comment{issue.comments !== 1 ? "s" : ""}
              </span>
              .{" "}
              <a
                href={`https://github.com/${owner}/${repo}/issues/${issue.number}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:underline"
              >
                View full discussion on GitHub →
              </a>
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// Icons
function IssueOpenIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
      <path d="M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" />
      <path
        fillRule="evenodd"
        d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z"
      />
    </svg>
  );
}

function IssueClosedIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 16 16">
      <path d="M11.28 6.78a.75.75 0 00-1.06-1.06L7.25 8.69 5.78 7.22a.75.75 0 00-1.06 1.06l2 2a.75.75 0 001.06 0l3.5-3.5z" />
      <path
        fillRule="evenodd"
        d="M16 8A8 8 0 110 8a8 8 0 0116 0zm-1.5 0a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z"
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
