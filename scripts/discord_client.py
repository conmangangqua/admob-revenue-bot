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
    if low.startswith("bbl"):
        return "bbl"
    if low.startswith("affica"):
        return "affica"
    if low.startswith("herond"):
        return "herond"
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
    """▲ +12.3% / ▼ -8.1% / 🆕 khi hôm trước = 0."""
    if prev <= 0:
        return "🆕" if cur > 0 else ""
    pct = (cur - prev) / prev * 100
    return f"{'▲' if pct >= 0 else '▼'} {pct:+.1f}%"


def _build_revenue_fields(apps_data: list, prev_total: Optional[float]) -> list:
    """v6.0: fields doanh thu GA từ apps_data bot vừa quét (KHÔNG phụ thuộc API)."""
    fields = []
    total = sum(a["revenue"] for a in apps_data)
    head = f"**${total:,.2f}**"
    if prev_total and prev_total > 0:
        head += f"  ({_pct_arrow(total, prev_total)} so với hôm trước ${prev_total:,.2f})"
    n_apps = len([a for a in apps_data if a["revenue"] > 0])
    head += f"\n📱 {n_apps} app có doanh thu"
    fields.append({"name": "💰 Tổng doanh thu ads", "value": head[:1024], "inline": False})

    top = sorted(apps_data, key=lambda a: -a["revenue"])[:10]
    lines = []
    for i, a in enumerate(top, 1):
        if a["revenue"] <= 0:
            break
        arrow = _pct_arrow(a["revenue"], a.get("prev_revenue", 0))
        lines.append(f"`{i:>2}.` **{a['app_name']}** — `${a['revenue']:,.2f}` {arrow}")
    if lines:
        fields.append({"name": "🏆 Top app", "value": "\n".join(lines)[:1024], "inline": False})

    # Gom doanh thu theo partner (prefix tên)
    by_partner = {}
    for a in apps_data:
        if a["revenue"] <= 0:
            continue
        by_partner.setdefault(_get_partner(a["app_name"]), 0.0)
        by_partner[_get_partner(a["app_name"])] += a["revenue"]
    if by_partner:
        pl = [f"{PARTNER_DISPLAY[p]['emoji']} {PARTNER_DISPLAY[p]['label']} `${v:,.0f}`"
              for p, v in sorted(by_partner.items(), key=lambda x: -x[1])]
        fields.append({"name": "🌍 Doanh thu theo đối tác",
                       "value": " · ".join(pl)[:1024], "inline": False})
    return fields


def _build_embed(history: dict, target_date: date,
                 apps_data=None, prev_total: Optional[float] = None) -> dict:
    d = target_date
    fields = []
    color = 0x3B82F6
    total_profit = 0.0

    # --- v6.0: khối DOANH THU từ dữ liệu GA bot vừa quét (nguồn chính) ---
    if apps_data:
        fields += _build_revenue_fields(apps_data, prev_total)

    def _pl(profit: float) -> str:
        return (f"💚 LÃI `{_fmt_trvnd(profit)}`" if profit >= 0
                else f"🔻 LỖ `{_fmt_trvnd(profit)}`")

    # --- Khối LÃI/LỖ từ history API (sheet-enriched) — best effort ---
    target = target_date.isoformat()
    if history:
        if target not in history:
            prior = [k for k in history.keys() if k <= target]
            target = sorted(prior)[-1] if prior else sorted(history.keys())[-1]
        apps = history[target].get("apps", []) or []
        partners = _aggregate(apps)
        total_profit = sum(p["profit_trvnd"] for p in partners.values() if p["has_profit"])
        color = 0x10B981 if total_profit > 0 else (0xEF4444 if total_profit < 0 else 0x3B82F6)
        d = datetime.fromisoformat(target).date()
    else:
        partners = {}

    # --- Lãi/Lỗ HÔM NAY (chỉ partner có đủ data lãi/lỗ) ---
    order = sorted(partners.keys(), key=lambda p: partners[p]["profit_trvnd"], reverse=True)
    today_lines = []
    for p in order:
        e = partners[p]
        if not e["has_profit"]:
            continue
        meta = PARTNER_DISPLAY[p]
        today_lines.append(f"{meta['emoji']} **{meta['label']}** — {_pl(e['profit_trvnd'])}")
    if today_lines:
        value = (f"**Tổng:** {_pl(total_profit)}\n" + "\n".join(today_lines))
        fields.append({
            "name": "💹 Hôm nay",
            "value": value[:1024],
            "inline": False,
        })

    # --- Lãi/Lỗ LŨY KẾ (chỉ partner có đủ data lãi/lỗ) ---
    month_start = d.replace(day=1).isoformat()
    summary_partners = [
        ("azura",  month_start,  f"tháng {d.strftime('%m')}"),
        ("bbl",    month_start,  f"tháng {d.strftime('%m')}"),
        ("herond", month_start,  f"tháng {d.strftime('%m')}"),
        ("affica", month_start,  f"tháng {d.strftime('%m')}"),
    ]
    sum_lines = []
    for p, start_iso, label in summary_partners:
        rev, spend, profit, has_profit, days = _sum_range(history, p, start_iso, target)
        if not has_profit:
            continue
        meta = PARTNER_DISPLAY[p]
        sum_lines.append(f"{meta['emoji']} **{meta['label']}** ({label}) — {_pl(profit)}")
    if sum_lines:
        fields.append({
            "name": "📅 Lãi / Lỗ lũy kế",
            "value": "\n".join(sum_lines)[:1024],
            "inline": False,
        })

    fields.append({
        "name": "🔗 Chi tiết",
        "value": "👉 [Doanh thu & từng app trên Web App](https://admob-revenue-bot.vercel.app/)",
        "inline": False,
    })

    return {
        "title": f"💹 Tranquil Revenue — {_day_name_vn(d)}, {d.strftime('%d/%m/%Y')}",
        "url": "https://admob-revenue-bot.vercel.app/",
        "color": color,
        "fields": fields,
        "footer": {"text": "🤖 v6.0 · GA4 Data API (SA) · Lãi thực (Tr VND) từ sheet"},
        "timestamp": f"{d.isoformat()}T01:00:00Z",
    }


# ---------- Public API (compat with main.py) ----------
def send_revenue_report(
    webhook_url: str,
    apps_data=None,            # v6.0: dữ liệu GA bot vừa quét — NGUỒN CHÍNH của embed
    report_date: Optional[date] = None,
    prev_total: Optional[float] = None,
    api_url: str = API_URL,
) -> bool:
    """Gửi report: khối doanh thu build từ apps_data (GA4, số bot vừa quét);
    khối Lãi/Lỗ build từ history API sheet-enriched (best effort — API sập
    vẫn gửi phần doanh thu)."""
    if report_date is None:
        report_date = date.today() - timedelta(days=1)

    try:
        history = _fetch_history(api_url)
    except Exception as e:
        print(f"   ⚠️ Fetch API failed ({e}) — gửi report chỉ với dữ liệu GA.")
        history = {}

    embed = _build_embed(history, report_date, apps_data=apps_data, prev_total=prev_total)
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
