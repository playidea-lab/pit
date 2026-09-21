import Link from "next/link";
import { getDecision } from "@/lib/api";
import Markdown from "@/components/Markdown";

interface PageProps {
  params: Promise<{
    owner: string;
    repo: string;
    decisionId: string;
  }>;
}

export default async function DecisionPage({ params }: PageProps) {
  const { owner, repo, decisionId } = await params;
  const decision = await getDecision(owner, repo, decisionId);

  if (!decision) {
    return (
      <main className="min-h-screen bg-gray-900 text-white p-8">
        <div className="max-w-4xl mx-auto text-center py-20">
          <h1 className="text-3xl font-bold mb-4">Decision Not Found</h1>
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
        {/* Decision Header */}
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-2">
            <span className="text-gray-500">{decision.id}</span>
            {decision.status && (
              <span className="px-2 py-1 rounded text-xs bg-purple-600">
                {decision.status}
              </span>
            )}
          </div>
          <h1 className="text-3xl font-bold">{decision.title}</h1>
        </div>

        {/* Content */}
        <article className="bg-gray-800 rounded-lg p-6">
          <Markdown content={decision.content} />
        </article>

        {/* Metadata */}
        {decision.created_at && (
          <div className="mt-8 text-sm text-gray-500">
            Created: {new Date(decision.created_at).toLocaleString()}
          </div>
        )}
      </div>
    </main>
  );
}
