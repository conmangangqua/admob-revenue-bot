import { clearCookieHeader } from "../../lib/session.js";

export default async function handler(req, res) {
  res.setHeader("Set-Cookie", clearCookieHeader());
  // Redirect login page hoặc /
  res.writeHead(302, { Location: "/login.html" });
  res.end();
}
