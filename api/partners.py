from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request


def _norm_app(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _build_partner_map():
    """Mirror scripts/discord_client._snapshot_partner_map():
    {tên chuẩn hoá: partner_key} lấy từ snapshot apps-status — nguồn CHÂN LÝ về đối tác.
    Khớp cả slug, name lẫn GA property_name của từng app."""
    out = {}
    tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(
        "https://raw.githubusercontent.com/conmangangqua/apps-status/data/snapshot.json",
        headers={"Authorization": f"token {tok}"} if tok else {},
    )
    snap = json.loads(urllib.request.urlopen(req, timeout=25).read())
    for p in snap.get("partners", []):
        key = (p.get("slug") or "").lower().replace(" ", "_").replace("-", "_")
        if key in ("no_channel", ""):
            continue
        if key == "adc_media":
            key = "adc"
        for a in (p.get("apps") or []):
            ga = ((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}
            for nm in (a.get("slug"), a.get("name"), ga.get("property_name")):
                if nm:
                    out[_norm_app(nm)] = key
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            pmap = _build_partner_map()
            body = json.dumps(pmap).encode("utf-8")
            status = 200
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode("utf-8")
            status = 200  # trả rỗng-an-toàn để web fallback về prefix, không vỡ dashboard
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
