const DEFAULT_API_URL = "http://localhost:8000";

export const ODIN_API_URL = (
  process.env.NEXT_PUBLIC_ODIN_API_URL ?? DEFAULT_API_URL
).replace(/\/$/, "");

export class OdinApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "OdinApiError";
  }
}

export async function odinFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(`${ODIN_API_URL}${normalizedPath}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init.headers,
    },
    cache: "no-store",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new OdinApiError(
      `Odin API request failed with status ${response.status}`,
      response.status,
      payload,
    );
  }

  return payload as T;
}
