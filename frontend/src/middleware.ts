import { NextResponse, type NextRequest } from "next/server";

// Map product subdomains to internal routes. Apex / preview / localhost pass through.
const HOST_ROUTE: Record<string, string> = {
  patient: "/patient",
  clinic: "/clinic",
  dashboard: "/xray",
};

export function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const sub = host.split(".")[0];
  const base = HOST_ROUTE[sub];
  if (!base) return NextResponse.next();

  const { pathname } = request.nextUrl;
  // Only rewrite the bare root of a product subdomain to its surface.
  if (pathname === "/") {
    const url = request.nextUrl.clone();
    url.pathname = base;
    return NextResponse.rewrite(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|api|favicon.ico).*)"],
};
