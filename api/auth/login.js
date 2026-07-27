// Bắt đầu Google OAuth flow — redirect user → Google consent screen.
import { ALLOWED_DOMAIN } from "../../lib/session.js";

export default async function handler(req, res) {
  const clientId = process.env.GOOGLE_OAUTH_CLIENT_ID;
  if (!clientId) {
    return res.status(500).send("GOOGLE_OAUTH_CLIENT_ID chưa set trong Vercel env.");
  }
  const proto = req.headers["x-forwarded-proto"] || "https";
  const host = req.headers.host;
  const redirectUri = `${proto}://${host}/api/auth/callback`;
  // Pass-through target URL sau khi login xong (default: /).
  const next = (req.query?.next || "/").toString().slice(0, 200);
  // CSRF state — random + lưu trong cookie để verify ở callback.
  const state = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64url") + "|" + Buffer.from(next).toString("base64url");
  res.setHeader("Set-Cookie", `ag_oauth_state=${state}; Path=/; Max-Age=600; HttpOnly; Secure; SameSite=Lax`);

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid email profile",
    access_type: "online",
    prompt: "select_account",
    hd: ALLOWED_DOMAIN, // Google chỉ hiện account thuộc Workspace tranquilmind.co (hint, không bypass được)
    state,
  });

  res.writeHead(302, { Location: `https://accounts.google.com/o/oauth2/v2/auth?${params}` });
  res.end();
}
