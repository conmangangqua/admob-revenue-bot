"""
get_refresh_token.py
Chạy 1 LẦN DUY NHẤT trên máy local để lấy Refresh Token.
Sau đó lưu token vào GitHub Secrets, không cần chạy lại.

Cách dùng:
  python3 get_refresh_token.py
  python3 get_refresh_token.py --client-id YOUR_ID --client-secret YOUR_SECRET
"""
import argparse
import json
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT_URI = "http://localhost:8080"
SCOPE = " ".join([
    "https://www.googleapis.com/auth/firebase.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
])


def main():
    parser = argparse.ArgumentParser(description="Lấy AdMob Refresh Token")
    parser.add_argument("--client-id", default="", help="OAuth2 Client ID")
    parser.add_argument("--client-secret", default="", help="OAuth2 Client Secret")
    args = parser.parse_args()

    print("=" * 55)
    print("  AdMob OAuth2 - Lấy Refresh Token (1 lần duy nhất)")
    print("=" * 55)
    print()
    client_id = args.client_id or input("📌 Nhập Client ID: ").strip()
    client_secret = args.client_secret or input("📌 Nhập Client Secret: ").strip()

    auth_url = (
        f"https://accounts.google.com/o/oauth2/auth"
        f"?client_id={urllib.parse.quote(client_id)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPE)}"
        f"&response_type=code"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print("\n🌐 Đang mở trình duyệt để xác thực Google...")
    webbrowser.open(auth_url)
    print("   (Nếu trình duyệt không mở, copy URL sau vào browser:)")
    print(f"   {auth_url}\n")

    auth_code = [None]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            auth_code[0] = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"<h2>&#10003; Xac thuc thanh cong! Quay lai terminal.</h2>"
            )

        def log_message(self, format, *args):
            pass

    print("⏳ Đang chờ xác thực (server localhost:8080)...")
    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()

    if not auth_code[0]:
        print("❌ Không lấy được auth code. Thử lại.")
        return

    # Đổi code lấy tokens
    data = urllib.parse.urlencode(
        {
            "code": auth_code[0],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"❌ Lỗi khi đổi token: {e.read().decode()}")
        return

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("❌ Không có refresh_token trong response. Đảm bảo đã dùng ?prompt=consent")
        return

    print()
    print("=" * 55)
    print("  ✅ THÀNH CÔNG! Lưu các giá trị sau vào GitHub Secrets:")
    print("=" * 55)
    print(f"\n  ADMOB_CLIENT_ID     = {client_id}")
    print(f"  ADMOB_CLIENT_SECRET = {client_secret}")
    print(f"  ADMOB_REFRESH_TOKEN = {refresh_token}")
    print()
    print("📌 Vào: GitHub Repo → Settings → Secrets → Actions → New secret")
    print("=" * 55)


if __name__ == "__main__":
    main()
