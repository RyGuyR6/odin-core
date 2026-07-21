import { NextRequest, NextResponse } from "next/server";

const API_URL =
  process.env.ODIN_API_URL ??
  process.env.NEXT_PUBLIC_ODIN_API_URL ??
  "https://odin-api-63t2.onrender.com";

type ChatRequest = {
  message?: string;
  conversationId?: string | null;
};

async function apiFetch(path: string, init?: RequestInit) {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  const text = await response.text();
  let body: unknown = null;

  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text || "Unexpected response from Odin API." };
  }

  if (!response.ok) {
    const detail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Odin API returned ${response.status}.`;

    throw new Error(detail);
  }

  return body;
}

export async function POST(request: NextRequest) {
  try {
    const payload = (await request.json()) as ChatRequest;
    const message = payload.message?.trim();

    if (!message) {
      return NextResponse.json(
        { detail: "Message is required." },
        { status: 400 },
      );
    }

    let conversationId = payload.conversationId ?? null;

    if (!conversationId) {
      const conversation = (await apiFetch("/conversations", {
        method: "POST",
        body: JSON.stringify({
          title: message.slice(0, 72),
          metadata: { source: "odin-web-native-chat" },
        }),
      })) as { id: string };

      conversationId = conversation.id;
    }

    const result = (await apiFetch(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          role: "user",
          content: message,
          generate_reply: true,
        }),
      },
    )) as {
      assistant_message?: {
        content?: string;
      };
    };

    return NextResponse.json({
      conversationId,
      reply:
        result.assistant_message?.content ??
        "Odin returned no assistant message.",
    });
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : "Native chat request failed.";

    return NextResponse.json({ detail }, { status: 502 });
  }
}
