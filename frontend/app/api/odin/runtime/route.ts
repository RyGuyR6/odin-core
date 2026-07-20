import { NextResponse } from "next/server";
import { odinConfig } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET() {
  const started = Date.now();
  const url = `${odinConfig.apiUrl}/runtime/dashboard`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    const body = await response.json().catch(() => ({ detail: "Invalid runtime response" }));
    return NextResponse.json(
      { ...body, proxy: { latencyMs: Date.now() - started, checkedAt: new Date().toISOString() } },
      { status: response.status },
    );
  } catch (error) {
    return NextResponse.json(
      { detail: "Odin runtime API is unavailable.", error: error instanceof Error ? error.message : "Unknown error" },
      { status: 503 },
    );
  } finally { clearTimeout(timeout); }
}
