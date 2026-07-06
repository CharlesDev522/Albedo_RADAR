import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Resolve FastAPI base URL at request time (Docker sets API_URL when the container starts). */
function backendOrigin(): string {
  const raw =
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000/api/v1";
  return raw.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
}

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const url = new URL(req.url);
  const target = `${backendOrigin()}/api/v1/${path}${url.search}`;

  const headers = new Headers();
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);

  let body: ArrayBuffer | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    body = await req.arrayBuffer();
  }

  const maxAttempts = 3;
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const upstream = await fetch(target, {
        method: req.method,
        headers,
        body,
        cache: "no-store",
      });

      const responseHeaders = new Headers();
      for (const key of ["content-type", "cache-control", "connection", "x-accel-buffering"]) {
        const value = upstream.headers.get(key);
        if (value) responseHeaders.set(key, value);
      }

      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: responseHeaders,
      });
    } catch (error) {
      lastError = error;
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, attempt * 500));
      }
    }
  }

  const message = lastError instanceof Error ? lastError.message : String(lastError);
  return NextResponse.json(
    {
      detail: `Cannot reach API at ${target}: ${message}. Check: docker compose ps api && docker compose logs api --tail 40 && curl -sf http://localhost:8000/health`,
    },
    { status: 502 },
  );
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, ctx: RouteContext) {
  const { path } = await ctx.params;
  return proxyRequest(req, path);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;
