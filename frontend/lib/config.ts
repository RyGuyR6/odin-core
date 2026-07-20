const DEFAULT_API_URL = "http://localhost:8000";

function normalizeUrl(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export const odinConfig = {
  appName: process.env.NEXT_PUBLIC_ODIN_APP_NAME?.trim() || "Odin",
  environment:
    process.env.NEXT_PUBLIC_ODIN_ENVIRONMENT?.trim() ||
    process.env.NODE_ENV ||
    "development",
  apiUrl: normalizeUrl(
    process.env.ODIN_API_URL ||
      process.env.NEXT_PUBLIC_ODIN_API_URL ||
      DEFAULT_API_URL,
  ),
  healthPaths: (
    process.env.ODIN_HEALTH_PATHS || "/health,/api/health,/runtime/health"
  )
    .split(",")
    .map((path) => path.trim())
    .filter(Boolean),
  healthTimeoutMs: Number(process.env.ODIN_HEALTH_TIMEOUT_MS || "3500"),
} as const;
