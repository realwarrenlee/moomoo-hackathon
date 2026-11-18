import { NextResponse } from "next/server"

export const dynamic = "force-dynamic"

const ALLOWED = new Set([
  "health",
  "overview",
  "portfolio",
  "risk",
  "agents",
  "analytics",
  "audit",
])

export async function GET(
  _request: Request,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params
  if (path.length !== 1 || !ALLOWED.has(path[0])) {
    return NextResponse.json({ detail: "Unknown dashboard route" }, { status: 404 })
  }

  const base = (
    process.env.MOOTRADE_API_URL?.trim() || "http://127.0.0.1:8000"
  ).replace(/\/+$/, "")
  const headers: Record<string, string> = { Accept: "application/json" }
  const token = process.env.MOOTRADE_DASHBOARD_TOKEN?.trim()
  if (token) headers.Authorization = `Bearer ${token}`

  try {
    const response = await fetch(`${base}/api/v1/${path[0]}`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(25_000),
    })
    const body = await response.text()
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
      },
    })
  } catch {
    return NextResponse.json(
      { detail: "MooTrade read-only API is unreachable" },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    )
  }
}
