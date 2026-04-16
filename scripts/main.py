"""
main.py — Entry point của Firebase Revenue Bot (v5.2 - Backfill Enabled)
Chạy hàng ngày qua GitHub Actions hoặc chạy Backfill thủ công.
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


def load_env(key: str, required: bool = True) -> str:
    val = os.environ.get(key, "").strip()
    if not val and required:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"   ⚠️ Thiếu biến môi trường: {key}")
        return ""
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
    total_rev = sum(app["revenue"] for app in apps_data)
    
    # Chỉ lưu các app có doanh thu để file JSON nhẹ nhàng
    history[date_key] = {
        "total": round(total_rev, 2),
        "apps": [
            {
                "name": app["app_name"],
                "rev": round(app["revenue"], 2),
                "imp": app["impressions"],
                "ecpm": round(app["ecpm"], 2)
            }
            for app in apps_data if app["revenue"] > 0
        ]
    }
    
    # Sắp xếp lại theo thời gian cho đẹp
    sorted_history = dict(sorted(history.items(), reverse=True))

    # Ghi lại file
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(sorted_history, f, indent=2, ensure_ascii=False)
    print(f"   💾 Đã lưu dữ liệu lịch sử ngày {date_key}")


def main():
    print("=" * 55)
    print("  📊 Firebase Revenue Bot — Bắt đầu chạy")
    print("=" * 55)

    client_id       = load_env("ADMOB_CLIENT_ID", required=False)
    client_secret   = load_env("ADMOB_CLIENT_SECRET", required=False)
    refresh_token   = load_env("ADMOB_REFRESH_TOKEN", required=False)
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    # Hỗ trợ Backfill qua DATE_OFFSET (mặc định 1 = hôm qua)
    offset = int(os.environ.get("DATE_OFFSET", "1"))
    target_date = date.today() - timedelta(days=offset)
    day_before  = target_date - timedelta(days=1)

    print(f"\n📅 Báo cáo ngày: {target_date.strftime('%d/%m/%Y')}")

    print("\n🔑 Đang kiểm tra quyền truy cập...")
    if not client_id or not client_secret or not refresh_token:
        # Giữ lại mock data CHỈ KHI Sếp muốn test (thiếu biến môi trường hoàn toàn)
        # Nhưng nếu Sếp đã khai báo mà lỗi thì phải STOP.
        print("   ⚠️ Thiếu biến môi trường ADMOB_*. Vui lòng kiểm tra lại.")
        return

    try:
        access_token = get_access_token_local(client_id, client_secret, refresh_token)
        print("   ✅ Token OK")
    except Exception as e:
        # [BLOCKER] Không được bịa dữ liệu khi lỗi API
        error_detail = str(e)
        if "400" in error_detail:
            print(f"   ❌ Lỗi OAuth 400: Refresh Token có thể đã hết hạn hoặc bị thu hồi.")
            print(f"   💡 Gợi ý: Sếp hãy lấy lại Refresh Token mới từ Google Cloud Console.")
        else:
            print(f"   ❌ Lỗi lấy Token: {error_detail}")
        
        # Gửi thông báo lỗi lên Discord thay vì gửi report giả
        if discord_webhook:
            from discord_client import send_error_notification
            send_error_notification(discord_webhook, f"Bot dừng do lỗi Auth: {error_detail}")
        return

    print(f"\n📱 Đang lấy revenue ngày {target_date.strftime('%d/%m/%Y')} (tất cả Firebase projects)...")
    apps_today = get_all_projects_revenue(access_token, target_date)
    print("\n📊 Đang lấy revenue hôm kia (để so sánh)...")
    apps_prev  = get_all_projects_revenue(access_token, day_before)
    
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
