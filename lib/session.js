// HMAC-signed session cookie helper. Không phụ thuộc JWT lib bên ngoài.
// Cookie format: base64url(JSON payload).base64url(HMAC-SHA256)
const SECRET = process.env.AUTH_SECRET || "dev-secret-change-me";
const COOKIE_NAME = "ag_session";
const TTL_DAYS = 7;
const ALLOWED_DOMAIN = "tranquilmind.co";

async function _hmac(data) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", enc.encode(SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  return _b64url(new Uint8Array(sig));
}
function _b64url(buf) {
  const bin = String.fromCharCode(...buf);
  return btoa(bin).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}
function _b64urlJson(obj) {
  return _b64url(new TextEncoder().encode(JSON.stringify(obj)));
}
function _decodeB64urlJson(str) {
  const padded = str + "==".slice(0, (4 - str.length % 4) % 4);
  const b64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(Buffer.from(b64, "base64").toString("utf8"));
}

export async function createSessionCookie(payload) {
  const body = { ...payload, exp: Math.floor(Date.now() / 1000) + TTL_DAYS * 86400 };
  const head = _b64urlJson(body);
  const sig = await _hmac(head);
  return `${head}.${sig}`;
}

export async function verifySession(cookieValue) {
  if (!cookieValue) return null;
  const [head, sig] = cookieValue.split(".");
  if (!head || !sig) return null;
  const expectedSig = await _hmac(head);
  if (sig !== expectedSig) return null;
  let payload;
  try { payload = _decodeB64urlJson(head); } catch { return null; }
  if (payload.exp < Math.floor(Date.now() / 1000)) return null;
  return payload;
}

export function parseCookies(req) {
  const cookieHeader = req.headers?.cookie || req.headers?.get?.("cookie") || "";
  const out = {};
  for (const part of cookieHeader.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k) out[k] = decodeURIComponent(v.join("="));
  }
  return out;
}

export function sessionCookieHeader(value, maxAgeSec) {
  const flags = [
    `${COOKIE_NAME}=${value}`,
    "HttpOnly",
    "Secure",
    "Path=/",
    "SameSite=Lax",
    `Max-Age=${maxAgeSec ?? TTL_DAYS * 86400}`,
  ];
  return flags.join("; ");
}

export function clearCookieHeader() {
  return `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`;
}

export async function getSessionFromReq(req) {
  const cookies = parseCookies(req);
  return verifySession(cookies[COOKIE_NAME]);
}

export function isEmailAllowed(email) {
  if (!email) return false;
  const lower = email.toLowerCase();
  // Domain check
  if (lower.endsWith("@" + ALLOWED_DOMAIN)) return true;
  // Whitelist override qua env (comma-separated).
  const extras = (process.env.ALLOWED_EMAILS || "").toLowerCase().split(",").map(s => s.trim()).filter(Boolean);
  return extras.includes(lower);
}

export { COOKIE_NAME, ALLOWED_DOMAIN };
