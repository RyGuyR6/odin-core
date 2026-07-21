"use client";

import { useCallback, useEffect, useState } from "react";

type Repository = {
  github_id: number;
  full_name: string;
  owner: string;
  name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
  description?: string | null;
  connected?: boolean;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/repositories${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(options?.body ? { "content-type": "application/json" } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {}
    throw new Error(detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export default function RepositoriesPage() {
  const [connected, setConnected] = useState<Repository[]>([]);
  const [available, setAvailable] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [connectedResult, availableResult] = await Promise.all([
        request<{ repositories: Repository[] }>(""),
        request<{ repositories: Repository[] }>("/available"),
      ]);
      setConnected(connectedResult.repositories);
      setAvailable(availableResult.repositories);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load repositories");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Repository data is intentionally loaded when this route mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function connect(fullName: string) {
    setPending(fullName);
    setError("");
    try {
      await request("", {
        method: "POST",
        body: JSON.stringify({ full_name: fullName }),
      });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to connect repository");
    } finally {
      setPending(null);
    }
  }

  async function disconnect(fullName: string) {
    setPending(fullName);
    setError("");
    try {
      await request(`/${fullName}`, { method: "DELETE" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to disconnect repository");
    } finally {
      setPending(null);
    }
  }

  return (
    <main className="space-y-8 p-8 text-zinc-100">
      <header>
        <p className="text-sm font-medium text-violet-300">OW-005</p>
        <h1 className="mt-1 text-3xl font-semibold">Repository Connections</h1>
        <p className="mt-2 text-zinc-400">
          GitHub authentication and repository access are owned by Odin.
        </p>
      </header>

      {error && (
        <div className="rounded-xl border border-red-400/20 bg-red-400/10 p-4 text-red-200">
          {error}
        </div>
      )}

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold">Connected repositories</h2>
          <button
            onClick={() => void load()}
            className="rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="text-zinc-400">Loading repositories…</p>
        ) : connected.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 p-8 text-zinc-400">
            No repositories are connected yet.
          </div>
        ) : (
          <div className="grid gap-4">
            {connected.map((repository) => (
              <article
                key={repository.github_id}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <a
                      href={repository.html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-violet-200 hover:underline"
                    >
                      {repository.full_name}
                    </a>
                    <p className="mt-1 text-sm text-zinc-400">
                      {repository.description || "No description"}
                    </p>
                    <p className="mt-3 text-xs text-zinc-500">
                      Default branch: {repository.default_branch}
                      {repository.private ? " · Private" : " · Public"}
                    </p>
                  </div>
                  <button
                    disabled={pending === repository.full_name}
                    onClick={() => void disconnect(repository.full_name)}
                    className="rounded-lg border border-red-400/20 px-3 py-2 text-sm text-red-200 hover:bg-red-400/10 disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Available from GitHub</h2>
        <div className="grid gap-4">
          {available.map((repository) => (
            <article
              key={repository.github_id}
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-semibold">{repository.full_name}</p>
                  <p className="mt-1 text-sm text-zinc-400">
                    {repository.description || "No description"}
                  </p>
                </div>
                <button
                  disabled={repository.connected || pending === repository.full_name}
                  onClick={() => void connect(repository.full_name)}
                  className="rounded-lg bg-violet-300 px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
                >
                  {repository.connected ? "Connected" : "Connect"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
