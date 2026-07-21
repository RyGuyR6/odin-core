import type { AuthResponse, OdinUser } from "./types";

type RequestOptions = {
  method?: string;
  body?: unknown;
};

async function authRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetch(`/api/auth/${path}`, {
    method: options.method ?? "GET",
    headers:
      options.body === undefined
        ? undefined
        : { "content-type": "application/json" },
    body:
      options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Authentication request failed (${response.status})`;
    try {
      const payload = (await response.json()) as {
        detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
      };

      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail)) {
        message = payload.detail
          .map((item) => {
            const location = item.loc?.slice(1).join(".");
            return location ? `${location}: ${item.msg ?? "Invalid value"}` : item.msg;
          })
          .filter(Boolean)
          .join("; ");
      }
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const authClient = {
  bootstrapStatus: () =>
    authRequest<{ required: boolean }>("bootstrap/status"),
  bootstrap: (payload: {
    username: string;
    email: string;
    password: string;
  }) => authRequest<AuthResponse>("bootstrap", { method: "POST", body: payload }),
  login: (payload: {
    username: string;
    password: string;
  }) => authRequest<AuthResponse>("login", { method: "POST", body: payload }),
  logout: () => authRequest<void>("logout", { method: "POST" }),
  refresh: () => authRequest<AuthResponse>("refresh", { method: "POST" }),
  me: () => authRequest<OdinUser>("me"),
};
