import { NextResponse, type NextRequest } from "next/server";

// The /dev preview routes must not exist in a production deployment.
//
// `notFound()` inside the page is not sufficient on its own: it swaps in the 404
// *UI* but the response still goes out as HTTP 200 — a soft 404 that reads fine
// in a browser and wrong to anything checking status codes (monitors, crawlers,
// a smoke test asserting the route is gone). Verified by building and requesting
// it, both with and without `force-dynamic`; both returned 200.
//
// Middleware runs before the route is resolved, so it can set a real status.
// `notFound()` stays in the page as the second, independent guard.
export function middleware(_request: NextRequest) {
  if (process.env.NODE_ENV === "production") {
    return new NextResponse("Not found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/dev/:path*",
};
