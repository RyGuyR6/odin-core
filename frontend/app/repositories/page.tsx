"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";

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
  local_path?: string | null;
  scan_status?: string;
  scan_updated_at?: string | null;
  scan_completed_at?: string | null;
};

type MajorModule = {
  name: string;
  file_count: number;
};

type RepositorySummary = {
  project_purpose: string;
  languages: string[];
  frameworks: string[];
  architecture: string[];
  major_modules: MajorModule[];
  key_entry_points: string[];
  test_framework: string[];
  build_system: string[];
  package_manager: string[];
};

type FileNode = {
  name: string;
  path: string;
  type: "directory" | "file";
  children: FileNode[];
};

type ArchitectureCategory = {
  category: string;
  files: string[];
};

type DependencyEdge = {
  source: string;
  target: string;
  kind: string;
  external: boolean;
};

type DependencyGraph = {
  nodes: Array<{ id: string; label: string; kind: string }>;
  edges: DependencyEdge[];
  circular_dependencies: string[][];
  entry_points: string[];
};

type ScanStatus = {
  status: string;
  scan_started_at?: string | null;
  scan_completed_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  local_path?: string | null;
  indexed_revision?: string | null;
  summary?: RepositorySummary | null;
  architecture?: ArchitectureCategory[];
  metadata?: Record<string, unknown>;
};

type RepositoryStatus = {
  connected: boolean;
  repository: Repository;
  github: {
    default_branch: string;
    private: boolean;
    archived: boolean;
    disabled: boolean;
    open_issues_count: number;
    pushed_at: string;
  };
  intelligence: ScanStatus;
};

type SymbolRecord = {
  name: string;
  qualified_name: string;
  kind: string;
  file_path: string;
  line: number;
  container?: string | null;
};

type SymbolLookupResponse = {
  count: number;
  symbols: SymbolRecord[];
};

type RepositorySearchResult = {
  repository: string;
  file_path: string;
  symbol?: string | null;
  source_location?: { line?: number | null } | null;
  relevance_score: number;
  match_type: string;
  excerpt: string;
  indexed_revision?: string | null;
  language?: string | null;
  file_type?: string | null;
};

type RepositorySearchResponse = {
  count: number;
  results: RepositorySearchResult[];
  stale: boolean;
  indexed_revision?: string | null;
};

type DocumentationRecord = {
  path: string;
  line: number;
  title: string;
  kind: string;
  symbol?: string | null;
  excerpt: string;
};

type FileContentResponse = {
  repository: string;
  path: string;
  content: string;
  truncated: boolean;
  indexed_revision?: string | null;
};

type SymbolReference = {
  symbol: string;
  file_path: string;
  line: number;
  kind: string;
  excerpt: string;
};

type ImpactResponse = {
  path: string;
  dependencies: string[];
  dependents: string[];
  tests: string[];
};

type ScanResponse = {
  repository: string;
  local_path?: string | null;
  status: string;
  scan_started_at?: string | null;
  scan_completed_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  payload?: {
    summary: RepositorySummary;
    directory_tree: FileNode;
    architecture: ArchitectureCategory[];
    dependency_graph: DependencyGraph;
  };
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

function TreeNode({ node, depth = 0 }: { node: FileNode; depth?: number }) {
  const margin = { paddingLeft: `${depth * 0.9}rem` };
  if (node.type === "file") {
    return (
      <li className="truncate text-sm text-zinc-300" style={margin}>
        {node.name}
      </li>
    );
  }

  return (
    <li>
      <div className="truncate text-sm font-medium text-white" style={margin}>
        {node.path || node.name}
      </div>
      {node.children.length > 0 && (
        <ul className="mt-2 space-y-1">
          {node.children.map((child) => (
            <TreeNode key={`${child.path}-${child.type}`} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

function niceStatus(status?: string) {
  return status?.replace(/_/g, " ") ?? "unknown";
}

export default function RepositoriesPage() {
  const [connected, setConnected] = useState<Repository[]>([]);
  const [available, setAvailable] = useState<Repository[]>([]);
  const [selected, setSelected] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [status, setStatus] = useState<RepositoryStatus | null>(null);
  const [summary, setSummary] = useState<RepositorySummary | null>(null);
  const [tree, setTree] = useState<FileNode | null>(null);
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [architecture, setArchitecture] = useState<ArchitectureCategory[]>([]);
  const [symbols, setSymbols] = useState<SymbolRecord[]>([]);
  const [symbolQuery, setSymbolQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<RepositorySearchResult[]>([]);
  const [documentation, setDocumentation] = useState<DocumentationRecord[]>([]);
  const [fileContent, setFileContent] = useState<FileContentResponse | null>(null);
  const [references, setReferences] = useState<SymbolReference[]>([]);
  const [impact, setImpact] = useState<ImpactResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");

  const selectedRepository = useMemo(
    () => connected.find((repository) => repository.full_name === selected) ?? null,
    [connected, selected],
  );
  const selectedScanStatus = selectedRepository
    ? status?.intelligence.status ?? selectedRepository.scan_status ?? "unknown"
    : "no_selection";

  const clearDetails = useCallback(() => {
    setStatus(null);
    setSummary(null);
    setTree(null);
    setGraph(null);
    setArchitecture([]);
    setSymbols([]);
    setSearchResults([]);
    setDocumentation([]);
    setFileContent(null);
    setReferences([]);
    setImpact(null);
  }, []);

  const loadSymbols = useCallback(
    async (fullName: string, query = "") => {
      const search = new URLSearchParams();
      if (query) search.set("q", query);
      const suffix = search.size > 0 ? `?${search.toString()}` : "";
      const result = await request<SymbolLookupResponse>(`/${fullName}/symbols${suffix}`);
      setSymbols(result.symbols);
    },
    [],
  );

  const loadDocumentation = useCallback(async (fullName: string, query = "") => {
    const search = new URLSearchParams();
    if (query) search.set("q", query);
    const suffix = search.size > 0 ? `?${search.toString()}` : "";
    const result = await request<{ documents: DocumentationRecord[] }>(
      `/${fullName}/documentation${suffix}`,
    );
    setDocumentation(result.documents);
  }, []);

  const loadFile = useCallback(async (fullName: string, path: string) => {
    const search = new URLSearchParams({ path });
    const result = await request<FileContentResponse>(
      `/${fullName}/files?${search.toString()}`,
    );
    setFileContent(result);
    const impactResult = await request<ImpactResponse>(
      `/${fullName}/impact?${search.toString()}`,
    );
    setImpact(impactResult);
  }, []);

  const loadReferences = useCallback(async (fullName: string, symbol: string) => {
    const search = new URLSearchParams({ symbol });
    const result = await request<{ references: SymbolReference[] }>(
      `/${fullName}/references?${search.toString()}`,
    );
    setReferences(result.references);
  }, []);

  const searchRepository = useCallback(async (fullName: string, query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    const search = new URLSearchParams({ q: query.trim() });
    const result = await request<RepositorySearchResponse>(
      `/${fullName}/search?${search.toString()}`,
    );
    setSearchResults(result.results);
  }, []);

  const loadDetails = useCallback(
    async (fullName: string) => {
      setDetailsLoading(true);
      setFileContent(null);
      setReferences([]);
      setImpact(null);
      try {
        const repositoryStatus = await request<RepositoryStatus>(`/${fullName}/status`);
        setStatus(repositoryStatus);
        setLocalPath(repositoryStatus.repository.local_path ?? repositoryStatus.intelligence.local_path ?? "");

        if (repositoryStatus.intelligence.status === "ready") {
          const [summaryResult, treeResult, graphResult] = await Promise.all([
            request<RepositorySummary>(`/${fullName}/summary`),
            request<FileNode>(`/${fullName}/tree`),
            request<DependencyGraph>(`/${fullName}/dependency-graph`),
          ]);
          setSummary(summaryResult);
          setTree(treeResult);
          setGraph(graphResult);
          setArchitecture(repositoryStatus.intelligence.architecture ?? []);
          await loadSymbols(fullName, symbolQuery);
          await loadDocumentation(fullName);
        } else {
          setSummary(repositoryStatus.intelligence.summary ?? null);
          setTree(null);
          setGraph(null);
          setArchitecture(repositoryStatus.intelligence.architecture ?? []);
          setSymbols([]);
          setDocumentation([]);
        }
      } catch (reason) {
        setSummary(null);
        setTree(null);
        setGraph(null);
        setArchitecture([]);
        setSymbols([]);
        setError(reason instanceof Error ? reason.message : "Unable to load repository intelligence");
      } finally {
        setDetailsLoading(false);
      }
    },
    [loadDocumentation, loadSymbols, symbolQuery],
  );

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
      const nextSelected = connectedResult.repositories.some((repository) => repository.full_name === selected)
        ? selected
        : connectedResult.repositories[0]?.full_name ?? "";
      setSelected(nextSelected);
      if (!nextSelected) {
        clearDetails();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load repositories");
    } finally {
      setLoading(false);
    }
  }, [clearDetails, selected]);

  useEffect(() => {
    // Repository data is intentionally loaded when this route mounts.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    // Repository intelligence is intentionally refreshed whenever selection changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDetails(selected);
  }, [loadDetails, selected]);

  function chooseRepository(value: string) {
    setSelected(value);
    if (!value) {
      clearDetails();
    }
  }

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
      if (selected === fullName) {
        chooseRepository("");
      }
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to disconnect repository");
    } finally {
      setPending(null);
    }
  }

  async function scanSelectedRepository() {
    if (!selected) return;
    setScanning(true);
    setError("");
    try {
      const result = await request<ScanResponse>(`/${selected}/scan`, {
        method: "POST",
        body: JSON.stringify({ local_path: localPath || undefined }),
      });
      setSummary(result.payload?.summary ?? null);
      setTree(result.payload?.directory_tree ?? null);
      setGraph(result.payload?.dependency_graph ?? null);
      setArchitecture(result.payload?.architecture ?? []);
      setStatus((current) =>
        current
          ? {
              ...current,
              intelligence: {
                ...current.intelligence,
                status: result.status,
                local_path: result.local_path ?? localPath,
                summary: result.payload?.summary ?? current.intelligence.summary ?? null,
                architecture: result.payload?.architecture ?? current.intelligence.architecture ?? [],
              },
            }
          : current,
      );
      await Promise.all([
        load(),
        loadSymbols(selected, symbolQuery),
        loadDocumentation(selected, searchQuery),
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to scan repository");
    } finally {
      setScanning(false);
    }
  }

  async function searchSymbols() {
    if (!selected) return;
    try {
      await loadSymbols(selected, symbolQuery);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to search symbols");
    }
  }

  async function runRepositorySearch() {
    if (!selected) return;
    try {
      await Promise.all([
        searchRepository(selected, searchQuery),
        loadDocumentation(selected, searchQuery),
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to search repository");
    }
  }

  return (
    <div className="space-y-8 text-zinc-100">
      <PageHeader
        eyebrow="OIC-002 · Repository intelligence"
        title="Repository Intelligence"
        description="Scan connected repositories, persist architectural metadata, and expose summaries, dependency graphs, and symbol search for every Odin agent."
      />

      {error && (
        <div className="rounded-2xl border border-red-400/20 bg-red-400/10 p-4 text-sm text-red-100">
          {error}
        </div>
      )}

      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_auto_auto] lg:items-end">
          <label className="space-y-2 text-sm">
            <span className="text-zinc-300">Repository selector</span>
            <select
              value={selected}
              onChange={(event) => chooseRepository(event.target.value)}
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white"
            >
              <option value="">Select a connected repository</option>
              {connected.map((repository) => (
                <option key={repository.full_name} value={repository.full_name}>
                  {repository.full_name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm">
            <span className="text-zinc-300">Local path</span>
            <input
              value={localPath}
              onChange={(event) => setLocalPath(event.target.value)}
              placeholder="/absolute/path/to/repository"
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white placeholder:text-zinc-500"
            />
          </label>

          <button
            type="button"
            disabled={!selected || scanning}
            onClick={() => void scanSelectedRepository()}
            className="rounded-xl bg-violet-300 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
          >
            {scanning ? "Scanning…" : "Scan repository"}
          </button>

          <button
            type="button"
            onClick={() => void load()}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/5"
          >
            Refresh
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 text-sm text-zinc-300">
          <span className="rounded-full border border-white/10 px-3 py-1">
            Status: {detailsLoading ? "loading" : niceStatus(selectedScanStatus)}
          </span>
          {status?.intelligence.scan_completed_at && (
            <span className="rounded-full border border-white/10 px-3 py-1">
              Last scan: {new Date(status.intelligence.scan_completed_at).toLocaleString()}
            </span>
          )}
          {selectedRepository?.default_branch && (
            <span className="rounded-full border border-white/10 px-3 py-1">
              Default branch: {selectedRepository.default_branch}
            </span>
          )}
          {status?.intelligence.indexed_revision && (
            <span className="rounded-full border border-white/10 px-3 py-1">
              Indexed revision: {status.intelligence.indexed_revision.slice(0, 12)}
            </span>
          )}
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Repository summary</h2>
          {summary ? (
            <div className="mt-4 space-y-4">
              <p className="text-sm text-zinc-300">{summary.project_purpose}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Languages</p>
                  <p className="mt-2 text-sm text-white">{summary.languages.join(", ") || "None detected"}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Frameworks</p>
                  <p className="mt-2 text-sm text-white">{summary.frameworks.join(", ") || "None detected"}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Package manager</p>
                  <p className="mt-2 text-sm text-white">{summary.package_manager.join(", ") || "None detected"}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Build system</p>
                  <p className="mt-2 text-sm text-white">{summary.build_system.join(", ") || "None detected"}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Test framework</p>
                  <p className="mt-2 text-sm text-white">{summary.test_framework.join(", ") || "None detected"}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Architecture tags</p>
                  <p className="mt-2 text-sm text-white">{summary.architecture.join(", ") || "None detected"}</p>
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Run a scan to generate a structured repository summary.</p>
          )}
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Major modules & entry points</h2>
          {summary ? (
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Major modules</p>
                <ul className="mt-2 space-y-2 text-sm text-zinc-300">
                  {summary.major_modules.map((module) => (
                    <li key={module.name} className="flex items-center justify-between rounded-xl border border-white/10 px-3 py-2">
                      <span>{module.name}</span>
                      <span className="text-zinc-500">{module.file_count} files</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Key entry points</p>
                <ul className="mt-2 space-y-2 text-sm text-zinc-300">
                  {summary.key_entry_points.map((item) => (
                    <li key={item} className="rounded-xl border border-white/10 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Entry points appear after the first successful scan.</p>
          )}
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Architecture overview</h2>
          {architecture.length > 0 ? (
            <div className="mt-4 grid gap-4">
              {architecture.map((category) => (
                <div key={category.category} className="rounded-xl border border-white/10 p-4">
                  <div className="flex items-center justify-between gap-4">
                    <p className="font-medium capitalize text-white">{category.category.replace(/_/g, " ")}</p>
                    <span className="text-xs text-zinc-500">{category.files.length} files</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {category.files.slice(0, 8).map((file) => (
                      <span key={file} className="rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-300">
                        {file}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Architecture discovery results appear here after scanning.</p>
          )}
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Directory tree</h2>
          {tree ? (
            <div className="mt-4 max-h-[28rem] overflow-auto rounded-xl border border-white/10 p-4">
              <ul className="space-y-2">
                {tree.children.map((child) => (
                  <TreeNode key={`${child.path}-${child.type}`} node={child} />
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">File inventory and tree data appear here after scanning.</p>
          )}
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <h2 className="text-lg font-semibold">Repository search</h2>
              <p className="text-sm text-zinc-400">
                Hybrid file, symbol, lexical, documentation, and semantic search.
              </p>
            </div>
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search files, symbols, docs"
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white placeholder:text-zinc-500 sm:w-72"
            />
            <button
              type="button"
              disabled={!selected}
              onClick={() => void runRepositorySearch()}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-40"
            >
              Search
            </button>
          </div>
          {searchResults.length > 0 ? (
            <div className="mt-4 space-y-3">
              {searchResults.map((result) => (
                <button
                  type="button"
                  key={`${result.file_path}-${result.symbol ?? ""}-${result.match_type}-${result.source_location?.line ?? 0}`}
                  onClick={() => {
                    if (!selected) return;
                    void loadFile(selected, result.file_path);
                    if (result.symbol) {
                      void loadReferences(selected, result.symbol);
                    }
                  }}
                  className="block w-full rounded-xl border border-white/10 p-3 text-left hover:bg-white/[0.03]"
                >
                  <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span>{result.match_type}</span>
                    <span>•</span>
                    <span>{result.relevance_score.toFixed(1)}</span>
                  </div>
                  <p className="mt-2 text-sm font-medium text-white">
                    {result.symbol || result.file_path}
                  </p>
                  <p className="mt-1 text-xs text-zinc-400">
                    {result.file_path}
                    {result.source_location?.line ? `:${result.source_location.line}` : ""}
                  </p>
                  <p className="mt-2 line-clamp-3 text-sm text-zinc-300">
                    {result.excerpt}
                  </p>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Search results appear here.</p>
          )}
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Documentation browser</h2>
          {documentation.length > 0 ? (
            <div className="mt-4 space-y-3">
              {documentation.map((item) => (
                <button
                  type="button"
                  key={`${item.path}-${item.line}-${item.title}`}
                  onClick={() => {
                    if (!selected) return;
                    void loadFile(selected, item.path);
                    if (item.symbol) {
                      void loadReferences(selected, item.symbol);
                    }
                  }}
                  className="block w-full rounded-xl border border-white/10 p-3 text-left hover:bg-white/[0.03]"
                >
                  <p className="text-sm font-medium text-white">{item.title}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {item.path}:{item.line}
                  </p>
                  <p className="mt-2 line-clamp-4 text-sm text-zinc-300">
                    {item.excerpt}
                  </p>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Indexed docs and docstrings appear here.</p>
          )}
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Code viewer</h2>
          {fileContent ? (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                <span>{fileContent.path}</span>
                {fileContent.indexed_revision && (
                  <>
                    <span>•</span>
                    <span>{fileContent.indexed_revision.slice(0, 12)}</span>
                  </>
                )}
              </div>
              <pre className="max-h-[30rem] overflow-auto rounded-xl border border-white/10 bg-zinc-950 p-4 text-xs text-zinc-200">
                {fileContent.content}
              </pre>
              {fileContent.truncated && (
                <p className="text-xs text-zinc-500">File output truncated for display.</p>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Select a search result, symbol, or document to preview file content.</p>
          )}
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">References & impact</h2>
          <div className="mt-4 space-y-4">
            {references.length > 0 ? (
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Symbol references</p>
                <div className="mt-2 space-y-2">
                  {references.slice(0, 12).map((reference) => (
                    <button
                      type="button"
                      key={`${reference.file_path}-${reference.line}-${reference.symbol}`}
                      onClick={() => {
                        if (!selected) return;
                        void loadFile(selected, reference.file_path);
                      }}
                      className="block w-full rounded-xl border border-white/10 px-3 py-2 text-left hover:bg-white/[0.03]"
                    >
                      <p className="text-sm text-white">
                        {reference.file_path}:{reference.line}
                      </p>
                      <p className="mt-1 text-xs text-zinc-400">{reference.excerpt}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-400">Select a symbol to inspect indexed references.</p>
            )}

            {impact && (
              <div className="space-y-3">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Impact view</p>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs text-zinc-500">Dependencies</p>
                  <p className="mt-2 text-sm text-zinc-300">
                    {impact.dependencies.join(", ") || "None detected"}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs text-zinc-500">Dependents</p>
                  <p className="mt-2 text-sm text-zinc-300">
                    {impact.dependents.join(", ") || "None detected"}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs text-zinc-500">Likely tests</p>
                  <p className="mt-2 text-sm text-zinc-300">
                    {impact.tests.join(", ") || "None detected"}
                  </p>
                </div>
              </div>
            )}
          </div>
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="text-lg font-semibold">Dependency visualization</h2>
          {graph ? (
            <div className="mt-4 space-y-4 text-sm text-zinc-300">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Nodes</p>
                  <p className="mt-2 text-lg text-white">{graph.nodes.length}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Edges</p>
                  <p className="mt-2 text-lg text-white">{graph.edges.length}</p>
                </div>
                <div className="rounded-xl border border-white/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Circular dependencies</p>
                  <p className="mt-2 text-lg text-white">{graph.circular_dependencies.length}</p>
                </div>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Entry points</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {graph.entry_points.map((item) => (
                    <span key={item} className="rounded-full border border-white/10 px-3 py-1 text-xs text-zinc-300">
                      {item}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">File relationships</p>
                <ul className="mt-2 space-y-2">
                  {graph.edges.slice(0, 18).map((edge) => (
                    <li key={`${edge.source}-${edge.target}`} className="rounded-xl border border-white/10 px-3 py-2">
                      <span className="text-white">{edge.source}</span>
                      <span className="mx-2 text-zinc-500">→</span>
                      <span>{edge.target}</span>
                      {edge.external && <span className="ml-2 text-xs text-zinc-500">external</span>}
                    </li>
                  ))}
                </ul>
              </div>

              {graph.circular_dependencies.length > 0 && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-500">Circular dependencies</p>
                  <div className="mt-2 space-y-2">
                    {graph.circular_dependencies.map((cycle) => (
                      <div key={cycle.join("-")} className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-amber-100">
                        {cycle.join(" → ")}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Dependency graph data appears here after scanning.</p>
          )}
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <h2 className="text-lg font-semibold">Symbol search</h2>
              <p className="text-sm text-zinc-400">Search classes, interfaces, functions, methods, enums, and constants.</p>
            </div>
            <input
              value={symbolQuery}
              onChange={(event) => setSymbolQuery(event.target.value)}
              placeholder="Search symbol names"
              className="w-full rounded-xl border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white placeholder:text-zinc-500 sm:w-64"
            />
            <button
              type="button"
              disabled={!selected}
              onClick={() => void searchSymbols()}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-40"
            >
              Search
            </button>
          </div>

          {symbols.length > 0 ? (
            <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
              <table className="min-w-full divide-y divide-white/10 text-sm">
                <thead className="bg-white/[0.03] text-left text-zinc-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">Symbol</th>
                    <th className="px-3 py-2 font-medium">Kind</th>
                    <th className="px-3 py-2 font-medium">File</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {symbols.map((symbol) => (
                    <tr
                      key={`${symbol.qualified_name}-${symbol.file_path}-${symbol.line}`}
                      className="cursor-pointer hover:bg-white/[0.03]"
                      onClick={() => {
                        if (!selected) return;
                        void Promise.all([
                          loadReferences(selected, symbol.qualified_name),
                          loadFile(selected, symbol.file_path),
                        ]);
                      }}
                    >
                      <td className="px-3 py-2 text-white">
                        {symbol.qualified_name}
                        {symbol.container && <span className="ml-2 text-xs text-zinc-500">in {symbol.container}</span>}
                      </td>
                      <td className="px-3 py-2 text-zinc-300">{symbol.kind}</td>
                      <td className="px-3 py-2 text-zinc-300">
                        {symbol.file_path}:{symbol.line}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-4 text-sm text-zinc-400">Run a scan, then search for repository symbols.</p>
          )}
        </article>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Connected repositories</h2>
            {loading && <span className="text-sm text-zinc-500">Loading…</span>}
          </div>
          {connected.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-zinc-400">
              No repositories are connected yet.
            </div>
          ) : (
            <div className="grid gap-4">
              {connected.map((repository) => (
                <article key={repository.github_id} className="rounded-2xl border border-white/10 p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-2">
                      <a
                        href={repository.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold text-violet-200 hover:underline"
                      >
                        {repository.full_name}
                      </a>
                      <p className="text-sm text-zinc-400">{repository.description || "No description"}</p>
                      <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                        <span>Branch: {repository.default_branch}</span>
                        <span>•</span>
                        <span>{repository.private ? "Private" : "Public"}</span>
                        <span>•</span>
                        <span>Scan: {niceStatus(repository.scan_status)}</span>
                      </div>
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
        </article>

        <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h2 className="mb-4 text-lg font-semibold">Available from GitHub</h2>
          <div className="grid gap-4">
            {available.map((repository) => (
              <article key={repository.github_id} className="rounded-2xl border border-white/10 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="font-semibold text-white">{repository.full_name}</p>
                    <p className="mt-1 text-sm text-zinc-400">{repository.description || "No description"}</p>
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
        </article>
      </section>
    </div>
  );
}
