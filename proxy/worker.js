/**
 * Minimal CORS proxy for the NDAP Deep Research Agent demo.
 *
 * It forwards GET requests to the NDAP openapi host ONLY and adds CORS headers
 * so the static GitHub Pages frontend can read dataset rows from the browser.
 * It stores no secrets and no data — the browser builds the full NDAP URL from
 * the (publicly shipped) recipe and passes it as ?url=...
 *
 * Deploy:  cd proxy && npx wrangler deploy
 */

const ALLOWED_HOST = "loadqa.ndapapi.com";

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "*";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "GET") {
      return new Response("Only GET is allowed", { status: 405, headers: corsHeaders(origin) });
    }

    const target = new URL(request.url).searchParams.get("url");
    if (!target) {
      return new Response("Missing ?url= parameter", { status: 400, headers: corsHeaders(origin) });
    }

    let upstream;
    try {
      upstream = new URL(target);
    } catch {
      return new Response("Invalid url", { status: 400, headers: corsHeaders(origin) });
    }
    if (upstream.hostname !== ALLOWED_HOST) {
      return new Response(`Host not allowed: ${upstream.hostname}`, { status: 403, headers: corsHeaders(origin) });
    }

    const resp = await fetch(upstream.toString(), {
      headers: { "User-Agent": "Mozilla/5.0", Accept: "application/json" },
    });

    const headers = new Headers(corsHeaders(origin));
    headers.set("Content-Type", resp.headers.get("Content-Type") || "application/json");
    return new Response(resp.body, { status: resp.status, headers });
  },
};
