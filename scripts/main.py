"""
main.py — Entry point của AdMob Revenue Bot
Chạy hàng ngày lúc 8:00 AM giờ Việt Nam qua GitHub Actions.
"""
import os
import sys
import traceback
from datetime import date, timedelta

# Thêm thư mục scripts vào path
sys.path.insert(0, os.path.dirname(__file__))

from admob_client import get_access_token, list_accounts, get_network_report
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

    # Load secrets
    client_id = load_env("ADMOB_CLIENT_ID")
    client_secret = load_env("ADMOB_CLIENT_SECRET")
    refresh_token = load_env("ADMOB_REFRESH_TOKEN")
    discord_webhook = load_env("DISCORD_WEBHOOK_URL")

    yesterday = date.today() - timedelta(days=1)
    day_before = date.today() - timedelta(days=2)

    print(f"\n📅 Báo cáo ngày: {yesterday.strftime('%d/%m/%Y')}")

    # Lấy access token
    print("\n🔑 Đang lấy access token...")
    access_token = get_access_token(client_id, client_secret, refresh_token)
    print("   ✅ Token OK")

    # List tất cả publisher accounts
    print("\n📋 Đang lấy danh sách AdMob accounts...")
    accounts = list_accounts(access_token)

    if not accounts:
        msg = "Không tìm thấy AdMob publisher account nào."
        print(f"   ⚠️  {msg}")
        send_error_notification(discord_webhook, msg)
        return

    # Fetch revenue từng account
    all_apps_today: list[dict] = []
    prev_total_revenue = 0.0

    for account in accounts:
        publisher_id = account.get("publisherId", "")
        account_name = account.get("name", publisher_id)
        print(f"\n   🏢 Account: {account_name} ({publisher_id})")

        # Hôm qua
        print(f"      Fetching {yesterday}...")
        apps_today = get_network_report(access_token, publisher_id, yesterday)
        all_apps_today.extend(apps_today)
        print(f"      → {len(apps_today)} app(s), revenue: ${sum(a['revenue'] for a in apps_today):.2f}")

        # Hôm kia (để so sánh %)
        print(f"      Fetching {day_before} (so sánh)...")
        apps_prev = get_network_report(access_token, publisher_id, day_before)
        prev_total_revenue += sum(a["revenue"] for a in apps_prev)

    # Tổng hợp
    total_today = sum(a["revenue"] for a in all_apps_today)
    print(f"\n{'=' * 55}")
    print(f"  💰 Tổng revenue hôm qua : ${total_today:.2f}")
    print(f"  📊 Tổng revenue hôm kia  : ${prev_total_revenue:.2f}")
    print(f"  📱 Số apps               : {len(all_apps_today)}")
    print(f"{'=' * 55}\n")

    # Gửi Discord
    print("📨 Đang gửi báo cáo lên Discord...")
    success = send_revenue_report(
        webhook_url=discord_webhook,
        apps_data=all_apps_today,
        report_date=yesterday,
        prev_total=prev_total_revenue if prev_total_revenue > 0 else None,
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
        # Cố gắng notify Discord nếu có webhook
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
