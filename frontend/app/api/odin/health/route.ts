import { NextResponse } from "next/server";
import { odinConfig } from "@/lib/config";

type Attempt = {
  path: string;
  status?: number;
  error?: string;
};

export const dynamic = "force-dynamic";

export async function GET() {
  const startedAt = Date.now();
  const attempts: Attempt[] = [];

  for (const path of odinConfig.healthPaths) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const url = `${odinConfig.apiUrl}${normalizedPath}`;
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(),
      odinConfig.healthTimeoutMs,
    );

    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });

      attempts.push({ path: normalizedPath, status: response.status });

      if (response.ok) {
        let upstream: unknown = null;
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          upstream = await response.json().catch(() => null);
        }

        return NextResponse.json({
          ok: true,
          state: "connected",
          apiUrl: odinConfig.apiUrl,
          endpoint: normalizedPath,
          latencyMs: Date.now() - startedAt,
          checkedAt: new Date().toISOString(),
          upstream,
        });
      }
    } catch (error) {
      attempts.push({
        path: normalizedPath,
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  return NextResponse.json(
    {
      ok: false,
      state: "unavailable",
      apiUrl: odinConfig.apiUrl,
      latencyMs: Date.now() - startedAt,
      checkedAt: new Date().toISOString(),
      attempts,
    },
    { status: 503 },
  );
}
