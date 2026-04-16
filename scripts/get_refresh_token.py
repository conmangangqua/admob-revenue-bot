import os
import urllib.parse
import urllib.request
import json

# === SCOPES CẦN THIẾT ===
SCOPES = [
    "https://www.googleapis.com/auth/admob.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/firebase.readonly",
    "https://www.googleapis.com/auth/cloud-platform"
]

def main():
    print("="*60)
    print("  🔑 TRÌNH LẤY REFRESH TOKEN CHO ADMOB BOT (PLATINUM)")
    print("="*60)

    # 1. Thu thập thông tin từ môi trường hoặc nhập tay
    client_id = os.environ.get("ADMOB_CLIENT_ID")
    client_secret = os.environ.get("ADMOB_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n❌ Lỗi: Thiếu ADMOB_CLIENT_ID hoặc ADMOB_CLIENT_SECRET trong môi trường.")
        client_id = input("👉 Nhập Client ID của Sếp: ").strip()
        client_secret = input("👉 Nhập Client Secret của Sếp: ").strip()

    # 2. Tạo URL Authorize
    params = {
        "client_id": client_id,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob", # Out-of-band (legacy but simple for local)
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    
    # URL OAuth 2.0 Auth
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    print("\n🚀 BƯỚC 1: Truy cập URL dưới đây bằng trình duyệt và đăng nhập:")
    print("-" * 20)
    print(auth_url)
    print("-" * 20)
    
    print("\n💡 Lưu ý: Nếu Google báo 'App not verified', sếp hãy nhấn 'Advanced' -> 'Go to (unsafe)' nhé.")

    # 3. Nhận Auth Code
    auth_code = input("\n👉 BƯỚC 2: Sau khi đồng ý, Sếp copy mã 'Authorization Code' và dán vào đây: ").strip()

    if not auth_code:
        print("❌ Sếp chưa nhập mã!")
        return

    # 4. Đổi Code lấy Token
    print("\n⏳ Đang trao đổi Token...")
    token_url = "https://oauth2.googleapis.com/token"
    token_params = {
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        "grant_type": "authorization_code"
    }
    
    data = urllib.parse.urlencode(token_params).encode()
    req = urllib.request.Request(token_url, data=data, method="POST")

    try:
        with urllib.request.urlopen(req) as r:
            res = json.loads(r.read())
            refresh_token = res.get("refresh_token")
            access_token = res.get("access_token")
            
            print("\n" + "✅ SUCCESS!" + " " + "="*50)
            print(f"👉 REFRESH TOKEN MỚI CỦA SẾP:\n\n{refresh_token}\n")
            print("="*60)
            print("💡 Sếp hãy copy mã trên và cập nhật vào ADMOB_REFRESH_TOKEN nhé!")
    except Exception as e:
        print(f"\n❌ Lỗi khi đổi token: {e}")
        print("Vui lòng kiểm tra lại Client ID / Secret và đảm bảo mã Auth Code chưa hết hạn.")

if __name__ == "__main__":
    main()
