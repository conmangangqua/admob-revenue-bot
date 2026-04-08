"""
main.py — Entry point của Firebase Revenue Bot (v5 - GA4 via Firebase)
Chạy hàng ngày qua GitHub Actions.
Dùng Firebase Management API → list tất cả projects → GA4 Data API lấy revenue.
"""
import os
import sys
import traceback
import urllib.parse
import urllib.request
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from firebase_client import get_all_projects_revenue
from discord_client import send_revenue_report, send_error_notification


def load_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(f"❌ Thiếu biến môi trường: {key}")
    return val


def get_access_token_local(client_id: str, client_secret: str, refresh_token: str) -> str:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def main():
    print("=" * 55)
    print("  📊 Firebase Revenue Bot — Bắt đầu chạy")
    print("=" * 55)

    client_id       = load_env("ADMOB_CLIENT_ID")
    client_secret   = load_env("ADMOB_CLIENT_SECRET")
    refresh_token   = load_env("ADMOB_REFRESH_TOKEN")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    yesterday  = date.today() - timedelta(days=1)
    day_before = date.today() - timedelta(days=2)

    print(f"\n📅 Báo cáo ngày: {yesterday.strftime('%d/%m/%Y')}")

    print("\n🔑 Đang lấy access token...")
    access_token = get_access_token_local(client_id, client_secret, refresh_token)
    print("   ✅ Token OK")

    # Lấy revenue của TẤT CẢ Firebase projects qua GA4
    print("\n📱 Đang lấy revenue hôm qua (tất cả Firebase projects)...")
    apps_today = get_all_projects_revenue(access_token, yesterday)

    print("\n📊 Đang lấy revenue hôm kia (để so sánh)...")
    apps_prev  = get_all_projects_revenue(access_token, day_before)
    prev_total = sum(a["revenue"] for a in apps_prev)

    total_today = sum(a["revenue"] for a in apps_today)
    app_count   = len([a for a in apps_today if a["revenue"] > 0])

    print(f"\n{'=' * 55}")
    print(f"  💰 Tổng revenue hôm qua : ${total_today:.2f}")
    print(f"  📊 Tổng revenue hôm kia  : ${prev_total:.2f}")
    print(f"  📱 Số app có revenue     : {app_count}")
    print(f"{'=' * 55}\n")

    if not discord_webhook:
        print("⚠️  Không có DISCORD_WEBHOOK_URL — bỏ qua gửi Discord.")
        print("\n✅ Data OK — Hoàn tất (không gửi Discord)!")
        return

    print("📨 Đang gửi báo cáo lên Discord...")
    success = send_revenue_report(
        webhook_url=discord_webhook,
        apps_data=apps_today,
        report_date=yesterday,
        prev_total=prev_total if prev_total > 0 else None,
    )

    if success:
        print("\n✅ Hoàn tất!")
    else:
        # Discord fail → chỉ warn, không crash workflow
        print("\n⚠️  Gửi Discord thất bại — nhưng data đã lấy thành công.")
        print("   👉 Sếp cần tạo lại Discord Webhook và update GitHub Secret DISCORD_WEBHOOK_URL")


if __name__ == "__main__":
    try:
        main()
    except EnvironmentError as e:
        print(str(e))
        webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        if webhook:
            send_error_notification(webhook, str(e))
        sys.exit(1)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        print(f"❌ Lỗi không xác định:\n{error_msg}")
        webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        if webhook:
            send_error_notification(webhook, error_msg)
        sys.exit(1)
