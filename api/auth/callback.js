// Nhận redirect từ Google sau khi user accept.
// Steps: verify state CSRF → exchange code → fetch userinfo → check email domain → set cookie.
import { createSessionCookie, sessionCookieHeader, parseCookies, isEmailAllowed, ALLOWED_DOMAIN } from "../../lib/session.js";

export default async function handler(req, res) {
  const { code, state, error } = req.query || {};
  if (error) return _denyHtml(res, "Google từ chối", `${error}`);
  if (!code || !state) return _denyHtml(res, "Thiếu param", "code/state trống");

  // CSRF: verify state vừa cookie vừa query.
  const cookies = parseCookies(req);
  const cookieState = cookies.ag_oauth_state;
  if (!cookieState || cookieState !== state) {
    return _denyHtml(res, "State sai", "CSRF check fail — login lại");
  }
  // Lấy `next` param đã encode trong state.
  const [, nextB64] = state.split("|");
  let next = "/";
  try { next = Buffer.from(nextB64, "base64url").toString("utf8") || "/"; } catch {}
  if (!next.startsWith("/")) next = "/"; // chống open-redirect

  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    return _denyHtml(res, "Env thiếu", "GOOGLE_OAUTH_CLIENT_ID hoặc SECRET chưa set");
  }
  const proto = req.headers["x-forwarded-proto"] || "https";
  const host = req.headers.host;
  const redirectUri = `${proto}://${host}/api/auth/callback`;

  // Step 1: exchange code → access_token.
  let tokenData;
  try {
    const r = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        grant_type: "authorization_code",
      }),
    });
    if (!r.ok) {
      const txt = await r.text();
      return _denyHtml(res, "Exchange fail", txt.slice(0, 200));
    }
    tokenData = await r.json();
  } catch (e) {
    return _denyHtml(res, "Network err", e.message);
  }

  // Step 2: fetch userinfo (email + name + picture).
  const userR = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: `Bearer ${tokenData.access_token}` },
  });
  if (!userR.ok) return _denyHtml(res, "User info fail", await userR.text());
  const user = await userR.json();

  // Step 3: verify email domain (hd claim hoặc email suffix).
  if (!isEmailAllowed(user.email)) {
    return _denyHtml(
      res,
      "Không có quyền truy cập",
      `Tài khoản <code>${user.email}</code> không thuộc <code>@${ALLOWED_DOMAIN}</code>. Liên hệ admin để được cấp quyền.`
    );
  }

  // Step 4: tạo session cookie + redirect về `next`.
  const session = await createSessionCookie({
    email: user.email,
    name: user.name || user.email.split("@")[0],
    picture: user.picture || null,
  });

  res.setHeader("Set-Cookie", [
    sessionCookieHeader(session),
    "ag_oauth_state=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax", // clear state cookie
  ]);
  res.writeHead(302, { Location: next });
  res.end();
}

function _denyHtml(res, title, detail) {
  res.status(403);
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.end(`<!doctype html><html lang="vi"><meta charset="utf-8"><title>${title}</title>
<style>body{font-family:system-ui;background:#0F0E2A;color:#E2E8F0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{max-width:480px;text-align:center;padding:32px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}
h1{color:#EF4444;margin:0 0 12px}p{color:#94A3B8;line-height:1.6}code{background:rgba(255,255,255,.06);padding:2px 6px;border-radius:4px;color:#A78BFA}
a{display:inline-block;margin-top:20px;padding:10px 20px;background:linear-gradient(135deg,#6366F1,#8B5CF6);color:#fff;text-decoration:none;border-radius:8px;font-weight:600}</style>
<div class="box"><h1>${title}</h1><p>${detail}</p><a href="/api/auth/login">Thử lại</a></div>`);
}
