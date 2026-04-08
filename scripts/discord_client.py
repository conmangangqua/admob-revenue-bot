"""
discord_client.py
Gửi báo cáo revenue hàng ngày lên Discord qua Webhook.
Format: Embed đẹp với màu xanh/đỏ tùy tăng/giảm so hôm qua.
"""
import json
import urllib.request
import urllib.error
from datetime import date
from typing import Optional


def _format_revenue(amount: float) -> str:
    if amount >= 1000:
        return f"${amount:,.2f}"
    return f"${amount:.2f}"


def _day_name_vn(d: date) -> str:
    days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]
    return days[d.weekday()]


def send_revenue_report(
    webhook_url: str,
    apps_data: list[dict],
    report_date: date,
    prev_total: Optional[float] = None,
) -> bool:
    """
    Gửi báo cáo revenue lên Discord.
    apps_data: list {app_name, revenue, impressions, ecpm}
    prev_total: tổng revenue ngày hôm trước để tính % thay đổi
    """
    # Sắp xếp theo revenue giảm dần
    apps_sorted = sorted(apps_data, key=lambda x: x["revenue"], reverse=True)

    total_revenue = sum(a["revenue"] for a in apps_data)
    total_impressions = sum(a["impressions"] for a in apps_data)
    num_apps = len(apps_data)

    # Màu và indicator thay đổi
    if prev_total and prev_total > 0:
        change_pct = ((total_revenue - prev_total) / prev_total) * 100
        if change_pct >= 0:
            color = 0x00C853  # Xanh lá
            trend_icon = "📈"
            trend_str = f"+{change_pct:.1f}%"
        else:
            color = 0xF44336  # Đỏ
            trend_icon = "📉"
            trend_str = f"{change_pct:.1f}%"
        vs_str = f"{trend_icon} **{trend_str}** so hôm qua (${prev_total:.2f})"
    else:
        color = 0x2196F3  # Xanh dương
        vs_str = "📊 Không có dữ liệu so sánh"

    date_str = report_date.strftime("%d/%m/%Y")
    day_name = _day_name_vn(report_date)

    # Build fields - mỗi app 1 dòng (tối đa 25 fields Discord)
    fields = []

    # Field tổng quan đầu tiên
    fields.append(
        {
            "name": "📊 Tổng Quan",
            "value": (
                f"💰 **Tổng Revenue:** `{_format_revenue(total_revenue)}`\n"
                f"👁 **Impressions:** `{total_impressions:,}`\n"
                f"{vs_str}"
            ),
            "inline": False,
        }
    )

    # Từng app dồn vào 1 field duy nhất (compact)
    if apps_sorted:
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, app in enumerate(apps_sorted[:20]):
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            bar = _mini_bar(app["revenue"], total_revenue)
            ecpm_str = f"${app['ecpm']:.2f}" if app["ecpm"] > 0 else "$0.00"
            imp_str = f"{app['impressions']:,}" if app["impressions"] else "0"
            lines.append(
                f"{rank} **{app['app_name'][:25]}**\n"
                f"   💵 `{_format_revenue(app['revenue'])}` {bar} · eCPM `{ecpm_str}` · 👁 `{imp_str}`"
            )

        fields.append({
            "name": f"📱 {len([a for a in apps_sorted if a['revenue'] > 0])} Apps có revenue",
            "value": "\n".join(lines) or "_Không có data_",
            "inline": False,
        })

    if len(apps_sorted) > 20:
        fields.append({
            "name": "...",
            "value": f"Và {len(apps_sorted) - 20} app khác",
            "inline": False,
        })


    embed = {
        "title": f"💹 AdMob Revenue — {day_name}, {date_str}",
        "color": color,
        "fields": fields,
        "footer": {
            "text": "🤖 AdMob Revenue Bot • Dữ liệu từ Google AdMob API",
        },
        "timestamp": f"{report_date.isoformat()}T01:00:00Z",
    }

    payload = {
        "username": "AdMob Revenue Bot",
        "embeds": [embed],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "DiscordBot (https://github.com/conmangangqua/admob-revenue-bot, 1.0)"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            # Discord trả 204 No Content khi thành công
            print(f"   ✅ Discord report gửi thành công! (status {resp.status})")
            return True
    except urllib.error.HTTPError as e:
        error = e.read().decode()
        print(f"   ❌ Discord webhook error {e.code}: {error[:300]}")
        return False


def _mini_bar(value: float, total: float, length: int = 8) -> str:
    """Thanh progress mini bằng ký tự unicode."""
    if total <= 0:
        return "░" * length
    filled = round((value / total) * length)
    return "█" * filled + "░" * (length - filled)


def send_error_notification(webhook_url: str, error_message: str) -> None:
    """Gửi thông báo lỗi lên Discord khi script fail."""
    embed = {
        "title": "⚠️ AdMob Revenue Bot — Lỗi",
        "description": f"```\n{error_message[:1500]}\n```",
        "color": 0xFF6B35,
        "footer": {"text": "Kiểm tra GitHub Actions logs để biết thêm chi tiết"},
    }
    payload = {
        "username": "AdMob Revenue Bot 📊",
        "embeds": [embed],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "DiscordBot (https://github.com/conmangangqua/admob-revenue-bot, 1.0)"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
    except Exception:
        pass
