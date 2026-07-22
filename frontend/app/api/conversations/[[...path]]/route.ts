import { NextRequest, NextResponse } from "next/server";

const backendUrl = (
  process.env.ODIN_BACKEND_URL ??
  process.env.NEXT_PUBLIC_ODIN_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const { path = [] } = await context.params;
  const suffix = path.length ? `/${path.join("/")}` : "";
  const target = `${backendUrl}/conversations${suffix}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const cookie = request.headers.get("cookie");
  if (contentType) headers.set("content-type", contentType);
  if (cookie) headers.set("cookie", cookie);

  const method = request.method;
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstream = await fetch(target, {
    method,
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType)
    responseHeaders.set("content-type", upstreamContentType);

  return new NextResponse(
    upstream.status === 204 ? null : upstream.body,
    { status: upstream.status, headers: responseHeaders },
  );
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
