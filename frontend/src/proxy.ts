import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  if (!request.cookies.has("gw_session")) {
    return NextResponse.redirect(new URL("/?access=required", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/lobby/:path*",
};
