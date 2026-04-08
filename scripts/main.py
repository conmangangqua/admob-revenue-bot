"""
main.py — Entry point của AdMob Revenue Bot (v4 - AdMob Native API)
Chạy hàng ngày qua GitHub Actions.
Dùng AdMob API trực tiếp: list accounts → network report theo ngày.
Không phụ thuộc GA4 property permissions.
"""
import os
import sys
import traceback
from datetime import date, timedelta

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

    client_id       = load_env("ADMOB_CLIENT_ID")
    client_secret   = load_env("ADMOB_CLIENT_SECRET")
    refresh_token   = load_env("ADMOB_REFRESH_TOKEN")
    discord_webhook = load_env("DISCORD_WEBHOOK_URL")

    yesterday  = date.today() - timedelta(days=1)
    day_before = date.today() - timedelta(days=2)

    print(f"\n📅 Báo cáo ngày: {yesterday.strftime('%d/%m/%Y')}")

    print("\n🔑 Đang lấy access token...")
    access_token = get_access_token(client_id, client_secret, refresh_token)
    print("   ✅ Token OK")

    # ---------- Lấy danh sách publisher accounts ----------
    accounts = list_accounts(access_token)
    if not accounts:
        raise RuntimeError("Không tìm thấy AdMob publisher account nào!")

    # ---------- Lấy revenue hôm qua ----------
    print(f"\n📱 Đang lấy revenue ngày {yesterday.strftime('%d/%m/%Y')}...")
    apps_today: list[dict] = []
    for acc in accounts:
        pub_id = acc.get("publisherId", acc.get("name", "").split("/")[-1])
        print(f"   🏢 Account: {pub_id}")
        rows = get_network_report(access_token, pub_id, yesterday)
        apps_today.extend(rows)

    # ---------- Lấy revenue hôm kia (để so sánh) ----------
    print(f"\n📊 Đang lấy revenue ngày {day_before.strftime('%d/%m/%Y')} (so sánh)...")
    apps_prev: list[dict] = []
    for acc in accounts:
        pub_id = acc.get("publisherId", acc.get("name", "").split("/")[-1])
        rows = get_network_report(access_token, pub_id, day_before)
        apps_prev.extend(rows)

    # ---------- Tổng kết ----------
    total_today = sum(a["revenue"] for a in apps_today)
    prev_total  = sum(a["revenue"] for a in apps_prev)
    app_count   = len([a for a in apps_today if a["revenue"] > 0])

    # In chi tiết từng app
    print()
    for app in sorted(apps_today, key=lambda x: x["revenue"], reverse=True):
        print(
            f"   💰 {app['app_name']}: ${app['revenue']:.2f}"
            f"  eCPM ${app['ecpm']:.2f}"
            f"  👁 {app['impressions']:,}"
        )

    print(f"\n{'=' * 55}")
    print(f"  💰 Tổng revenue hôm qua : ${total_today:.2f}")
    print(f"  📊 Tổng revenue hôm kia  : ${prev_total:.2f}")
    print(f"  📱 Số app có revenue     : {app_count}")
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
