import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth", "/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PATHS.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );

  if (isPublic) {
    return NextResponse.next();
  }

  const hasSession =
    request.cookies.has("odin_access") ||
    request.cookies.has("odin_refresh");

  if (!hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", path);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!.*\\..*).*)"],
};
