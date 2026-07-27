// Vercel Edge Middleware — chặn mọi request chưa login.
// Native Vercel Edge API (không cần Next.js).
export const config = {
  matcher: "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|svg|css|js|woff2?)$).*)",
};

const COOKIE_NAME = "ag_session";

const PUBLIC_PATHS = new Set([
  "/login.html",
  "/login",
  "/api/auth/login",
  "/api/auth/callback",
  "/api/auth/logout",
]);

function parseCookies(cookieHeader) {
  const out = {};
  for (const part of (cookieHeader || "").split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k) out[k] = v.join("=");
  }
  return out;
}

async function verifySession(cookieValue, secret) {
  if (!cookieValue) return null;
  const [head, sig] = cookieValue.split(".");
  if (!head || !sig) return null;
  const enc = new TextEncoder();
  try {
    const key = await crypto.subtle.importKey(
      "raw", enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false, ["verify"]
    );
    const sigB64 = sig.replace(/-/g, "+").replace(/_/g, "/");
    const sigPadded = sigB64 + "==".slice(0, (4 - sigB64.length % 4) % 4);
    const sigBytes = Uint8Array.from(atob(sigPadded), c => c.charCodeAt(0));
    const ok = await crypto.subtle.verify("HMAC", key, sigBytes, enc.encode(head));
    if (!ok) return null;
    const headB64 = head.replace(/-/g, "+").replace(/_/g, "/");
    const headPadded = headB64 + "==".slice(0, (4 - headB64.length % 4) % 4);
    const payload = JSON.parse(atob(headPadded));
    if (payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch { return null; }
}

export default async function middleware(req) {
  const url = new URL(req.url);
  const { pathname, search } = url;
  if (PUBLIC_PATHS.has(pathname)) return;  // pass through

  const cookies = parseCookies(req.headers.get("cookie"));
  const session = await verifySession(cookies[COOKIE_NAME], process.env.AUTH_SECRET || "");

  if (session) return;  // authenticated → pass through

  // Chưa auth.
  if (pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ ok: false, error: "unauthenticated" }), {
      status: 401, headers: { "Content-Type": "application/json" },
    });
  }
  const loginUrl = new URL("/login.html", req.url);
  loginUrl.searchParams.set("next", pathname + search);
  return Response.redirect(loginUrl.toString(), 302);
}
