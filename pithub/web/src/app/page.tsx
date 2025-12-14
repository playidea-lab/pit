"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AuthButton from "@/components/AuthButton";

export default function Home() {
  const [repoUrl, setRepoUrl] = useState("");
  const router = useRouter();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // github.com/owner/repo 형식에서 owner/repo 추출
    const match = repoUrl.match(/github\.com\/([^\/]+)\/([^\/]+)/);
    if (match) {
      const [, owner, repo] = match;
      router.push(`/${owner}/${repo}`);
    } else if (repoUrl.includes("/")) {
      // owner/repo 형식 직접 입력
      router.push(`/${repoUrl}`);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white">
      {/* Header with Auth */}
      <header className="border-b border-gray-700">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold">
            <span className="text-blue-400">pit</span>hub
          </h1>
          <AuthButton />
        </div>
      </header>

      <div className="container mx-auto px-4 py-16">
        {/* Hero Section */}
        <div className="text-center mb-16">
          <h1 className="text-5xl font-bold mb-4">
            <span className="text-blue-400">pit</span>hub
          </h1>
          <p className="text-xl text-gray-300 mb-2">
            GitHub repo의 <code className="bg-gray-700 px-2 py-1 rounded">.pit/</code> 폴더를 웹으로 시각화
          </p>
          <p className="text-gray-400">
            개발자는 GitHub에서 코드를, 기획자는 pithub에서 기획을 본다
          </p>
        </div>

        {/* Search Box */}
        <div className="max-w-2xl mx-auto mb-16">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="github.com/owner/repo 또는 owner/repo"
              className="flex-1 px-4 py-3 rounded-lg bg-gray-700 border border-gray-600 focus:border-blue-400 focus:outline-none text-white placeholder-gray-400"
            />
            <button
              type="submit"
              className="px-6 py-3 bg-blue-500 hover:bg-blue-600 rounded-lg font-medium transition-colors"
            >
              View
            </button>
          </form>
          <p className="text-sm text-gray-500 mt-2 text-center">
            예: changmin/pit
          </p>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 max-w-4xl mx-auto">
          <FeatureCard
            icon="📋"
            title="Feature 관리"
            description="기획 → 개발 → 배포까지 Feature 단위로 추적"
          />
          <FeatureCard
            icon="📝"
            title="Decision 기록"
            description="왜 이런 결정을 했는지 맥락과 함께 저장"
          />
          <FeatureCard
            icon="🚦"
            title="헬스 체크"
            description="프로젝트 진행 상황을 한눈에 파악"
          />
        </div>

        {/* How it works */}
        <div className="mt-20 text-center">
          <h2 className="text-2xl font-bold mb-8">How it works</h2>
          <div className="flex items-center justify-center gap-4 text-lg">
            <code className="bg-gray-700 px-3 py-2 rounded">
              github.com/user/repo
            </code>
            <span className="text-2xl">→</span>
            <code className="bg-blue-600 px-3 py-2 rounded">
              pithub.io/user/repo
            </code>
          </div>
        </div>
      </div>
    </main>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <div className="text-4xl mb-4">{icon}</div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-gray-400">{description}</p>
    </div>
  );
}
