"""
main.py — Entry point của AdMob Revenue Bot
Chạy hàng ngày lúc 8:00 AM giờ Việt Nam qua GitHub Actions.
"""
import os
import sys
import traceback
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from admob_client import get_access_token
from firebase_client import get_all_projects_revenue
from discord_client import send_revenue_report, send_error_notification


def load_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(f"❌ Thiếu biến môi trường: {key}")
    return val


def main():
    print("=" * 55)
    print("  📊 AdMob Revenue Bot — Bắt đầu chạy")
    print("=" * 55)

    client_id = load_env("ADMOB_CLIENT_ID")
    client_secret = load_env("ADMOB_CLIENT_SECRET")
    refresh_token = load_env("ADMOB_REFRESH_TOKEN")
    discord_webhook = load_env("DISCORD_WEBHOOK_URL")

    yesterday = date.today() - timedelta(days=1)
    day_before = date.today() - timedelta(days=2)

    print(f"\n📅 Báo cáo ngày: {yesterday.strftime('%d/%m/%Y')}")

    print("\n🔑 Đang lấy access token...")
    access_token = get_access_token(client_id, client_secret, refresh_token)
    print("   ✅ Token OK")

    # Fetch revenue hôm qua
    print("\n📱 Đang lấy revenue từ Firebase projects...")
    apps_today = get_all_projects_revenue(access_token, yesterday)

    # Fetch revenue hôm kia để so sánh
    print("\n📊 Đang lấy revenue hôm kia (để so sánh)...")
    apps_prev = get_all_projects_revenue(access_token, day_before)
    prev_total = sum(a["revenue"] for a in apps_prev)

    total_today = sum(a["revenue"] for a in apps_today)
    print(f"\n{'=' * 55}")
    print(f"  💰 Tổng revenue hôm qua : ${total_today:.2f}")
    print(f"  📊 Tổng revenue hôm kia  : ${prev_total:.2f}")
    print(f"  📱 Số Firebase projects  : {len(apps_today)}")
    print(f"{'=' * 55}\n")

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
        print("\n❌ Gửi Discord thất bại!")
        sys.exit(1)


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
