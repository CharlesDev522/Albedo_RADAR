import { NextRequest, NextResponse } from "next/server";
import { localhostFallbackUrl, resolveBackendOrigin } from "@/lib/backendOrigin";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const PROXY_TIMEOUT_MS = 120_000;

async function fetchUpstream(target: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);
  try {
    return await fetch(target, { ...init, signal: controller.signal });
  } catch (error) {
    const fallback = localhostFallbackUrl(target);
    if (fallback) {
      return await fetch(fallback, { ...init, signal: controller.signal });
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function proxyRequest(req: NextRequest, pathSegments: string[]) {
  const path = pathSegments.join("/");
  const url = new URL(req.url);
  const target = `${resolveBackendOrigin()}/api/v1/${path}${url.search}`;

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
      const upstream = await fetchUpstream(target, {
        method: req.method,
        headers,
        body,
        cache: "no-store",
      });

      const responseHeaders = new Headers();
      for (const key of [
        "content-type",
        "content-disposition",
        "content-length",
        "x-export-filename",
        "cache-control",
        "connection",
        "x-accel-buffering",
      ]) {
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
      detail: `Cannot reach API at ${target}: ${message}. If using Docker: docker compose ps api && curl -sf http://localhost:8000/health && docker compose logs api --tail 40. If using npm run dev on the host, set API_URL=http://localhost:8000/api/v1 (not http://api:8000).`,
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
