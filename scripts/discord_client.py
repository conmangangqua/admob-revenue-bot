"""
discord_client.py
Gửi báo cáo revenue hàng ngày lên Discord — gom theo đối tác (partner),
hiển thị lãi/lỗ thực, summary all-time cho Azura + tháng cho partner khác.

Data source: fetch live từ Vercel API `/api/revenue` (đã enrich sheet_data
cho Quicksave + LunaAI, ngoài Looker data sẵn có cho Azura). Không tự lo
ghép sheet ở client.
"""
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Optional

API_URL = "https://admob-revenue-bot.vercel.app/api/revenue"
VND_RATE = 25400

# Partner mapping — mirror web dashboard getPartner()
PARTNER_MAP = {
    "Quicksave": "bbl",
    "Aura-Recover": "bbl",
    "Herond Snapvid": "herond",
    "LunaAi-Chat": "affica",
}
PARTNER_DISPLAY = {
    "azura":   {"label": "Azura",  "emoji": "🅰️"},
    "bbl":     {"label": "BBL",    "emoji": "🅱️"},
    "herond":  {"label": "Herond", "emoji": "🐝"},
    "affica":  {"label": "Affica", "emoji": "🌍"},
    "ntech":   {"label": "NTech",  "emoji": "🔵"},
    "adc":     {"label": "ADC",    "emoji": "🟠"},
    "unknown": {"label": "Khác",   "emoji": "❓"},
}


# ---------- Helpers ----------
def _day_name_vn(d: date) -> str:
    return ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"][d.weekday()]


def _is_azura_bcode(name: str) -> bool:
    return bool(name) and name.startswith("B") and len(name) > 1 and name[1].isdigit()


def _get_partner(app_name: str) -> str:
    if app_name in PARTNER_MAP:
        return PARTNER_MAP[app_name]
    if _is_azura_bcode(app_name):
        return "azura"
    # v6.0: tên từ GA (ga_names.json) mang prefix partner — suy trực tiếp
    low = (app_name or "").lower()
    if low.startswith("bbl") or low.startswith("bll"):  # bll-whispr = typo của bbl
        return "bbl"
    if low.startswith("affica"):
        return "affica"
    if low.startswith("herond"):
        return "herond"
    if low.startswith("ntech"):
        return "ntech"
    if low.startswith("adc"):
        return "adc"
    return "unknown"


def _parse_sheet_num(raw, app_name: str = "") -> float:
    """sheet_data → triệu VND. Mirror index.html sheetNum(): Azura parse trực
    tiếp; non-Azura strip + /1000 (sheet đơn vị nghìn)."""
    if raw in (None, "", 0, "0"):
        return 0.0
    s = str(raw).strip()
    if _is_azura_bcode(app_name):
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return 0.0
    neg = "-" in s
    digits = re.sub(r"[^0-9,]", "", s).replace(",", ".")
    try:
        n = float(digits)
    except ValueError:
        return 0.0
    if neg:
        n = -n
    return n / 1000.0


def _app_profit_trvnd(a):
    sd = (a.get("sheet_data") or {}).get("marketing_profit_vnd")
    if sd in (None, "", 0, "0"):
        return None
    v = _parse_sheet_num(sd, a.get("name", ""))
    return v if v != 0 else None


def _fmt_vnd_from_usd(usd: float) -> str:
    if usd == 0:
        return "0 đ"
    raw_vnd = usd * VND_RATE
    if abs(raw_vnd) < 1_000_000:
        return f"{round(raw_vnd):,} đ"
    return f"{raw_vnd / 1_000_000:,.2f} Tr"


def _fmt_trvnd(v: float) -> str:
    if v == 0:
        return "0 Tr"
    if abs(v) < 0.01:
        raw = v * 1_000_000
        sign = "+" if raw > 0 else ""
        return f"{sign}{round(raw):,} đ"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:,.2f} Tr"


def _aggregate(apps):
    parts = {}
    for a in apps:
        p = _get_partner(a.get("name", ""))
        e = parts.setdefault(p, {"rev": 0.0, "spend": 0.0, "profit_trvnd": 0.0, "has_profit": False, "apps": []})
        e["rev"] += float(a.get("rev") or 0)
        e["spend"] += sum(float(a.get(k) or 0) for k in ("google_spend", "mintegral_spend", "tiktok_spend", "facebook_spend"))
        ap = _app_profit_trvnd(a)
        if ap is not None:
            e["profit_trvnd"] += ap
            e["has_profit"] = True
        e["apps"].append(a)
    return parts


def _fetch_history(api_url: str) -> dict:
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 admob-revenue-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _sum_range(history: dict, partner: str, start_iso: str, end_iso: str):
    rev_usd = 0.0
    spend_usd = 0.0
    profit_tr = 0.0
    has_profit = False
    days = 0
    for k in sorted(history.keys()):
        if k < start_iso or k > end_iso:
            continue
        apps = history[k].get("apps", []) or []
        day_hit = False
        for a in apps:
            if _get_partner(a.get("name", "")) != partner:
                continue
            day_hit = True
            rev_usd += float(a.get("rev") or 0)
            spend_usd += sum(float(a.get(k2) or 0) for k2 in ("google_spend", "mintegral_spend", "tiktok_spend", "facebook_spend"))
            ap = _app_profit_trvnd(a)
            if ap is not None:
                profit_tr += ap
                has_profit = True
        if day_hit:
            days += 1
    return rev_usd, spend_usd, profit_tr, has_profit, days


# ---------- Embed builder ----------
def _pct_arrow(cur: float, prev: float) -> str:
    """📈 +12.3% / 📉 -8.1% / 🆕 khi hôm trước = 0."""
    if prev <= 0:
        return "🆕" if cur > 0 else ""
    pct = (cur - prev) / prev * 100
    return f"{'📈' if pct >= 0 else '📉'} {pct:+.1f}%"


def _share_bar(part: float, total: float, width: int = 10) -> str:
    """Thanh tỷ trọng ▰▰▰▱▱ + %."""
    if total <= 0:
        return ""
    share = part / total
    filled = max(1, round(share * width)) if part > 0 else 0
    return "▰" * filled + "▱" * (width - filled) + f" {share*100:.0f}%"


_RANK = ["🥇", "🥈", "🥉"]


_PREFIX_RE = re.compile(r"(?i)^(bbl|bll|affica|herond|ntech|adc(?:[ -]media)?)[ \-]+")

TOP_PER_PARTNER = 5  # số app hiện trong mỗi khối partner


def _short_name(name: str) -> str:
    """Bỏ prefix partner trong tên app (đã nằm trong khối partner rồi)."""
    return _PREFIX_RE.sub("", name).strip() or name


def _build_revenue_fields(apps_data: list, prev_total: Optional[float]) -> list:
    """v6.2 (Sếp chốt 2026-07-27): chia theo ĐỐI TÁC — mỗi partner 1 khối:
    header = tổng partner + %Δ, bên dưới top app của partner đó."""
    fields = []
    total = sum(a["revenue"] for a in apps_data)

    # Gom app theo partner
    groups = {}
    for a in apps_data:
        groups.setdefault(_get_partner(a["app_name"]), []).append(a)

    order = sorted(groups.items(),
                   key=lambda kv: -sum(a["revenue"] for a in kv[1]))
    for p, apps in order:
        p_total = sum(a["revenue"] for a in apps)
        if p_total < 1:
            continue
        p_prev = sum(a.get("prev_revenue", 0) for a in apps)
        meta = PARTNER_DISPLAY[p]
        name = f"{meta['emoji']}  {meta['label']}  ·  ${p_total:,.2f}"
        arrow = _pct_arrow(p_total, p_prev)
        if arrow:
            name += f"   {arrow}"

        # v6.4: ```ansi``` — tên+% xanh/đỏ theo tăng giảm, SỐ TIỀN vàng đậm
        G, R, Y, X = "\u001b[2;32m", "\u001b[2;31m", "\u001b[1;33m", "\u001b[0m"
        apps = sorted(apps, key=lambda a: -a["revenue"])
        rows = []
        for i, a in enumerate(apps[:TOP_PER_PARTNER]):
            if a["revenue"] < 0.01:
                break
            prev = a.get("prev_revenue", 0)
            up = a["revenue"] >= prev
            c = G if up else R
            pct = "   new" if prev <= 0 else f"{(a['revenue'] - prev) / prev * 100:+.1f}%"
            nm = _short_name(a["app_name"])[:17]
            money = f"${a['revenue']:,.2f}"
            rows.append(f"{i + 1}. {c}{nm:<17}{X} {Y}{money:>10}{X} {c}{pct:>8}{X}")
        rest = [a for a in apps[TOP_PER_PARTNER:] if a["revenue"] >= 0.01]
        if rest:
            money = f"${sum(a['revenue'] for a in rest):,.2f}"
            rows.append(f"   … +{len(rest)} app khác   {Y}{money:>10}{X}")
        value = f"`{_share_bar(p_total, total)}` tổng fleet\n"
        value += "```ansi\n" + "\n".join(rows) + "\n```"
        fields.append({"name": name[:256], "value": value[:1024] or "—",
                       "inline": False})
    return fields


def _build_embed(target_date: date, apps_data: list,
                 prev_total: Optional[float] = None) -> dict:
    """v6.1: embed thuần doanh thu ads từ apps_data (GA4) — Sếp chốt 2026-07-27
    bỏ khối Lãi/Lỗ sheet, tách partner NTech/ADC, ẩn partner < $1."""
    fields = _build_revenue_fields(apps_data, prev_total)
    fields.append({
        "name": "\u200b",
        "value": "🔗 [Chi tiết từng app trên Web App](https://admob-revenue-bot.vercel.app/)",
        "inline": False,
    })
    total = sum(a["revenue"] for a in apps_data)
    up = prev_total is None or total >= prev_total
    n_apps = len([a for a in apps_data if a["revenue"] > 0])
    desc = f"# ${total:,.2f}"
    if prev_total and prev_total > 0:
        desc += f"\n{_pct_arrow(total, prev_total)} so với hôm trước (${prev_total:,.2f}) · 📱 {n_apps} app"
    return {
        "title": f"💹 Tranquil Revenue — {_day_name_vn(target_date)}, {target_date.strftime('%d/%m/%Y')}",
        "url": "https://admob-revenue-bot.vercel.app/",
        "description": desc,
        "color": 0x10B981 if up else 0xEF4444,
        "fields": fields,
        "footer": {"text": "🤖 v6.2 · GA4 Data API (service account)"},
        "timestamp": f"{target_date.isoformat()}T01:00:00Z",
    }


# ---------- Public API (compat with main.py) ----------
def send_revenue_report(
    webhook_url: str,
    apps_data=None,
    report_date: Optional[date] = None,
    prev_total: Optional[float] = None,
    api_url: str = API_URL,   # giữ tham số cho tương thích — không dùng nữa
) -> bool:
    """Gửi report doanh thu build 100% từ apps_data (GA4 bot vừa quét)."""
    if report_date is None:
        report_date = date.today() - timedelta(days=1)
    if not apps_data:
        print("   ❌ Không có apps_data — bỏ qua gửi Discord.")
        return False

    embed = _build_embed(report_date, apps_data, prev_total=prev_total)
    payload = {"username": "Tranquil Revenue Bot", "embeds": [embed]}

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/conmangangqua/admob-revenue-bot, 6.1)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"   ✅ Discord report gửi thành công! (status {r.status})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        print(f"   ❌ Discord webhook error {e.code}: {body[:300]}")
        return False


def send_error_notification(webhook_url: str, error_message: str) -> None:
    embed = {
        "title": "⚠️ Tranquil Revenue Bot — Lỗi",
        "description": f"```\n{error_message[:1500]}\n```",
        "color": 0xF44336,
    }
    payload = {"username": "Tranquil Revenue Bot", "embeds": [embed]}
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/conmangangqua/admob-revenue-bot, 6.0)",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass
