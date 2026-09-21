"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownProps {
  content: string;
}

export default function Markdown({ content }: MarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // 헤딩
        h1: ({ children }) => (
          <h1 className="text-2xl font-bold mt-6 mb-4 text-white border-b border-gray-700 pb-2">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-xl font-bold mt-5 mb-3 text-white">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-lg font-semibold mt-4 mb-2 text-white">
            {children}
          </h3>
        ),
        // 문단
        p: ({ children }) => (
          <p className="mb-4 text-gray-300 leading-relaxed">{children}</p>
        ),
        // 리스트
        ul: ({ children }) => (
          <ul className="list-disc list-inside mb-4 space-y-1 text-gray-300">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside mb-4 space-y-1 text-gray-300">
            {children}
          </ol>
        ),
        li: ({ children }) => <li className="ml-4">{children}</li>,
        // 코드
        code: ({ className, children }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code className="bg-gray-700 px-1.5 py-0.5 rounded text-sm text-blue-300">
                {children}
              </code>
            );
          }
          return (
            <code className="block bg-gray-900 p-4 rounded-lg overflow-x-auto text-sm text-gray-300">
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <pre className="bg-gray-900 rounded-lg mb-4 overflow-x-auto">
            {children}
          </pre>
        ),
        // 링크
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:underline"
          >
            {children}
          </a>
        ),
        // 인용
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 border-blue-500 pl-4 my-4 text-gray-400 italic">
            {children}
          </blockquote>
        ),
        // 테이블
        table: ({ children }) => (
          <div className="overflow-x-auto mb-4">
            <table className="min-w-full border border-gray-700 rounded-lg">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-gray-800">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-4 py-2 text-left text-white font-semibold border-b border-gray-700">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
            {children}
          </td>
        ),
        // 수평선
        hr: () => <hr className="my-6 border-gray-700" />,
        // 강조
        strong: ({ children }) => (
          <strong className="font-bold text-white">{children}</strong>
        ),
        em: ({ children }) => <em className="italic text-gray-200">{children}</em>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
