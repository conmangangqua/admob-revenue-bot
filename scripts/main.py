"""
main.py — Entry point của Revenue Bot (v6.0 — GA Account Direct)
Chạy hàng ngày qua GitHub Actions hoặc chạy Backfill thủ công.
v6.0 (2026-07-27): bỏ hẳn user refresh-token + firebase_client cũ.
Đọc thẳng GA4 Data API bằng SA hub-admin-sa (đã được add Viewer cấp GA account),
tự discover property qua accountSummaries — xem ga_client.py.
"""
import os
import sys
import traceback
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from ga_client import get_ga_token, get_all_revenue, get_total_revenue
from discord_client import send_revenue_report, send_error_notification


def save_historical_data(apps_data, report_date):
    """Lưu dữ liệu doanh thu vào file JSON lịch sử để Web Dashboard hiển thị."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_file = os.path.join(base_dir, "data", "revenue_history.json")
    
    # Đọc dữ liệu cũ nếu có
    history = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    # Chuẩn bị dữ liệu mới (theo ngày YYYY-MM-DD làm key)
    date_key = report_date.strftime("%Y-%m-%d")

    # MERGE thay vì replace: giữ lại app từ nguồn khác (Looker/Azura CSV) đã
    # sync vào cùng ngày — bot GA chỉ ghi đè các app do chính nó quản.
    ga_apps = {
        app["app_name"]: {
            "name": app["app_name"],
            "rev": round(app["revenue"], 2),
            "imp": app["impressions"],
            "ecpm": round(app["ecpm"], 2),
        }
        for app in apps_data if app["revenue"] > 0
    }
    merged = {a["name"]: a for a in history.get(date_key, {}).get("apps", [])}
    merged.update(ga_apps)
    apps_list = sorted(merged.values(), key=lambda a: -a["rev"])
    history[date_key] = {
        "total": round(sum(a["rev"] for a in apps_list), 2),
        "apps": apps_list,
    }
    
    # Sắp xếp lại theo thời gian cho đẹp
    sorted_history = dict(sorted(history.items(), reverse=True))

    # Ghi lại file
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(sorted_history, f, indent=2, ensure_ascii=False)
    print(f"   💾 Đã lưu dữ liệu lịch sử ngày {date_key}")


def main():
    print("=" * 55)
    print("  📊 GA Revenue Bot v6.0 — Bắt đầu chạy")
    print("=" * 55)

    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    # Hỗ trợ Backfill qua DATE_OFFSET (mặc định 1 = hôm qua)
    offset = int(os.environ.get("DATE_OFFSET", "1"))
    target_date = date.today() - timedelta(days=offset)
    day_before  = target_date - timedelta(days=1)

    print(f"\n📅 Báo cáo ngày: {target_date.strftime('%d/%m/%Y')}")

    print("\n🔑 Đang lấy token service account...")
    try:
        access_token = get_ga_token()
        print("   ✅ Token OK")
    except Exception as e:
        # [BLOCKER] Không được bịa dữ liệu khi lỗi API
        error_detail = str(e)
        print(f"   ❌ Lỗi Auth SA: {error_detail}")
        if discord_webhook:
            send_error_notification(discord_webhook, f"Bot dừng do lỗi Auth SA: {error_detail}")
        sys.exit(1)

    print(f"\n📱 Đang lấy revenue ngày {target_date.strftime('%d/%m/%Y')} (mọi GA property của SA)...")
    apps_today = get_all_revenue(access_token, target_date)
    print("\n📊 Đang lấy revenue hôm kia (để so sánh)...")
    apps_prev  = get_all_revenue(access_token, day_before)
    print("\n📆 Đang lấy tổng THÁNG NÀY (MTD, từ GA — history thời bot cũ thiếu số)...")
    mtd_total = get_total_revenue(access_token, target_date.replace(day=1), target_date)
    print(f"   ✅ MTD ${mtd_total:,.2f}")
    
    prev_total = sum(a["revenue"] for a in apps_prev)
    apps_prev_dict = {a["app_name"]: a["revenue"] for a in apps_prev}
    for app in apps_today:
        app["prev_revenue"] = apps_prev_dict.get(app["app_name"], 0.0)

    total_today = sum(a["revenue"] for a in apps_today)
    app_count   = len([a for a in apps_today if a["revenue"] > 0])

    print(f"\n{'=' * 55}")
    print(f"  💰 Tổng revenue hôm nay : ${total_today:.2f}")
    print(f"  📊 Tổng revenue hôm qua  : ${prev_total:.2f}")
    print(f"  📱 Số app có revenue     : {app_count}")
    print(f"{'=' * 55}\n")

    # Lưu dữ liệu vào file lịch sử
    print("\n📂 Đang lưu dữ liệu lịch sử...")
    save_historical_data(apps_today, target_date)

    # Refresh map logo app (data/app_icons.json) cho dashboard — không chặn nếu fail
    try:
        import gen_app_icons
        gen_app_icons.build()
    except Exception as e:
        print(f"⚠️  gen_app_icons fail (bỏ qua, dashboard fallback medal): {e}")

    # Kiểm tra tắt thông báo
    skip_notify = os.environ.get("SKIP_NOTIFY", "false").lower() == "true"
    if skip_notify:
        print("\n🔕 Chế độ SKIP_NOTIFY: Bỏ qua gửi thông báo Discord.")
        return

    if not discord_webhook:
        print("⚠️  Không có DISCORD_WEBHOOK_URL — bỏ qua gửi Discord.")
        return

    print("📨 Đang gửi báo cáo lên Discord...")
    success = send_revenue_report(
        webhook_url=discord_webhook,
        apps_data=apps_today,
        report_date=target_date,
        prev_total=prev_total if prev_total > 0 else None,
        mtd_total=mtd_total,
    )

    if success:
        print("\n✅ Hoàn tất gửi Discord!")
    else:
        print("\n⚠️  Gửi Discord thất bại.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        print(f"❌ Lỗi không xác định:\n{error_msg}")
        webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        if webhook:
            send_error_notification(webhook, error_msg)
        sys.exit(1)
