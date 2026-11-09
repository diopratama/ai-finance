import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function getBackendBase(): string {
  return (
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    (process.env.NODE_ENV === "production" ? "http://backend:8000" : "http://127.0.0.1:8001")
  ).replace(/\/+$/, "");
}

async function proxyRequest(
  request: NextRequest,
  context: { params: { path: string[] } } | { params: Promise<{ path: string[] }> }
): Promise<Response> {
  const resolvedParams = await Promise.resolve(context.params);
  const pathSegments = resolvedParams?.path || [];
  const targetUrl = `${getBackendBase()}/api/v1/${pathSegments.join("/")}${request.nextUrl.search}`;

  const upstreamHeaders = new Headers();
  const forwardNames = [
    "authorization",
    "content-type",
    "accept",
    "x-forwarded-for",
    "x-real-ip",
  ];
  for (const name of forwardNames) {
    const val = request.headers.get(name);
    if (val) upstreamHeaders.set(name, val);
  }

  let body: BodyInit | undefined = undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    const text = await request.text();
    if (text) body = text;
  }

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers: upstreamHeaders,
      body,
      cache: "no-store",
      signal: request.signal,
    });

    const resHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) resHeaders.set("Content-Type", contentType);
    if (contentType?.includes("text/event-stream")) {
      resHeaders.set("Cache-Control", "no-cache, no-transform");
      resHeaders.set("Connection", "keep-alive");
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: resHeaders,
    });
  } catch (err: any) {
    return Response.json(
      { detail: `Upstream backend unreachable: ${err?.message || "Unknown error"}` },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxyRequest(req, ctx);
}

export async function POST(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxyRequest(req, ctx);
}

export async function PUT(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxyRequest(req, ctx);
}

export async function DELETE(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxyRequest(req, ctx);
}

export async function PATCH(req: NextRequest, ctx: { params: { path: string[] } }) {
  return proxyRequest(req, ctx);
}

