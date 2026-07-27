import { getSessionFromReq } from "../../lib/session.js";

export default async function handler(req, res) {
  const session = await getSessionFromReq(req);
  if (!session) {
    res.status(401).json({ ok: false });
    return;
  }
  res.status(200).json({
    ok: true,
    email: session.email,
    name: session.name,
    picture: session.picture,
  });
}
