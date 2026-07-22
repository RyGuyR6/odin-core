"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

interface MarkdownContentProps {
  content: string;
}

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const code = String(children ?? "").replace(/\n$/, "");
  const lang = className?.replace("language-", "") ?? "code";

  function copy() {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="group relative my-3 rounded-xl border border-zinc-700 bg-zinc-900 text-sm">
      <div className="flex items-center justify-between border-b border-zinc-700 px-4 py-2">
        <span className="font-mono text-xs text-zinc-400">{lang}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-zinc-400 opacity-0 transition hover:bg-zinc-700 hover:text-white group-hover:opacity-100"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <Check size={12} />
              Copied
            </>
          ) : (
            <>
              <Copy size={12} />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 leading-6 text-zinc-100">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function InlineCode({ children }: { children?: React.ReactNode }) {
  return (
    <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[0.85em] text-violet-300">
      {children}
    </code>
  );
}

export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const isBlock = className?.startsWith("language-");
          if (isBlock) {
            return <CodeBlock className={className}>{children}</CodeBlock>;
          }
          return <InlineCode {...props}>{children}</InlineCode>;
        },
        p({ children }) {
          return <p className="mb-3 last:mb-0 leading-7">{children}</p>;
        },
        ul({ children }) {
          return (
            <ul className="mb-3 ml-4 list-disc space-y-1 leading-7">
              {children}
            </ul>
          );
        },
        ol({ children }) {
          return (
            <ol className="mb-3 ml-4 list-decimal space-y-1 leading-7">
              {children}
            </ol>
          );
        },
        li({ children }) {
          return <li className="leading-7">{children}</li>;
        },
        h1({ children }) {
          return (
            <h1 className="mb-3 mt-5 text-xl font-semibold">{children}</h1>
          );
        },
        h2({ children }) {
          return (
            <h2 className="mb-2 mt-4 text-lg font-semibold">{children}</h2>
          );
        },
        h3({ children }) {
          return (
            <h3 className="mb-2 mt-3 font-semibold">{children}</h3>
          );
        },
        blockquote({ children }) {
          return (
            <blockquote className="mb-3 border-l-2 border-violet-500 pl-4 text-zinc-400">
              {children}
            </blockquote>
          );
        },
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-violet-400 underline-offset-2 hover:underline"
            >
              {children}
            </a>
          );
        },
        hr() {
          return <hr className="my-4 border-zinc-700" />;
        },
        table({ children }) {
          return (
            <div className="mb-3 overflow-x-auto">
              <table className="min-w-full border-collapse border border-zinc-700 text-sm">
                {children}
              </table>
            </div>
          );
        },
        th({ children }) {
          return (
            <th className="border border-zinc-700 bg-zinc-800 px-3 py-2 text-left font-medium">
              {children}
            </th>
          );
        },
        td({ children }) {
          return (
            <td className="border border-zinc-700 px-3 py-2">{children}</td>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
