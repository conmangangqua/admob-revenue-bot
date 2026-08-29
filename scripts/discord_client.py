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
VND_RATE = 25400  # fallback; ghi đè bằng tỷ giá realtime khi bot khởi động


def refresh_vnd_rate() -> float:
    """Lấy tỷ giá USD→VND realtime (open.er-api.com, free no-key). Gọi 1 lần đầu
    mỗi run; lỗi/chậm → giữ fallback 25.400. Khớp nguồn với web dashboard."""
    global VND_RATE
    try:
        req = urllib.request.Request(
            "https://open.er-api.com/v6/latest/USD",
            headers={"User-Agent": "admob-revenue-bot"})
        with urllib.request.urlopen(req, timeout=8) as r:
            vnd = json.loads(r.read()).get("rates", {}).get("VND")
        if vnd and vnd > 0:
            VND_RATE = float(vnd)
            print(f"   💱 Tỷ giá realtime: 1$ = {round(VND_RATE):,}đ")
    except Exception as e:
        print(f"   ⚠️ Tỷ giá realtime fail ({e}) — dùng fallback {VND_RATE:,}đ")
    return VND_RATE


def _vnd(usd: float) -> str:
    """Tiền Việt compact: 1,23 Tỷ / 45,6 Tr / 123K đ."""
    vnd = usd * VND_RATE
    a = abs(vnd)
    if a >= 1_000_000_000:
        return f"{vnd/1_000_000_000:,.2f} Tỷ"
    if a >= 1_000_000:
        return f"{vnd/1_000_000:,.1f} Tr"
    if a >= 1_000:
        return f"{vnd/1_000:,.0f}K đ"
    return f"{round(vnd):,} đ"


def _money(usd: float) -> str:
    """Tiền Việt (đô) — VND là chính, USD trong ngoặc."""
    return f"{_vnd(usd)} (${usd:,.0f})"


# Partner mapping — mirror web dashboard getPartner()
PARTNER_MAP = {
    "Quicksave": "bbl",
    "Aura-Recover": "bbl",
    "Onyx Browser": "bbl",        # find_partner.py 2026-07-27
    "VaultixBrowser": "bbl",      # find_partner.py 2026-07-27
    "Herond Snapvid": "herond",
    "LunaAi-Chat": "affica",
}
PARTNER_DISPLAY = {
    "azura":   {"label": "AZURA",  "emoji": "💠"},
    "bbl":     {"label": "BBL",    "emoji": "🎯"},
    "herond":  {"label": "HEROND", "emoji": "🐝"},
    "affica":  {"label": "AFFICA", "emoji": "🌍"},
    "ntech":   {"label": "NTECH",  "emoji": "⚡"},
    "adc":     {"label": "ADC",    "emoji": "🎬"},
    "one_tabb":{"label": "ONE TABB","emoji": "📑"},
    "unknown": {"label": "KHÁC",   "emoji": "📦"},
}


# ---------- Helpers ----------
def _day_name_vn(d: date) -> str:
    return ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"][d.weekday()]


def _is_azura_bcode(name: str) -> bool:
    return bool(name) and name.startswith("B") and len(name) > 1 and name[1].isdigit()


# Sếp 2026-08-11 ("sao chapture lại là đối tác khác"): map partner CŨ đoán theo PREFIX tên
# app (bbl-, adc-, affica-…). App nào tên không mang prefix — như `chapture-tmt` — rơi thẳng
# vào nhóm "KHÁC" dù nó thuộc AFFICA. Đoán theo tên là sai gốc: nguồn chân lý về đối tác nằm
# ở snapshot apps-status (mỗi app nằm trong đúng partner của nó). Tra snapshot trước, prefix
# chỉ còn là lưới đỡ khi app chưa vào snapshot.
_SNAP_PARTNER = None


def _snapshot_partner_map():
    """{tên chuẩn hoá: partner_key} lấy từ snapshot — khớp cả slug, name lẫn GA property."""
    global _SNAP_PARTNER
    if _SNAP_PARTNER is not None:
        return _SNAP_PARTNER
    _SNAP_PARTNER = {}
    try:
        import os, json as _json, urllib.request as _u
        tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
        if not tok:
            # Sếp 2026-08-12 ("vẫn đối tác khác ???"): bản vá hôm qua KHÔNG ăn vì hàm này
            # chỉ đọc token từ ENV, mà job revenue-report-local chạy dưới launchd chỉ có
            # ANTIGRAVITY_ROOT/HOME/PATH ⇒ token rỗng ⇒ snapshot 401 ⇒ map RỖNG ⇒ mọi app
            # rơi về 'unknown'. Đúng cái bẫy đã cắn ở notify_router 05/08. Đọc thẳng
            # secrets.env, dò ngược lên như các script khác.
            for base in (os.environ.get("ANTIGRAVITY_ROOT", ""),
                         os.path.expanduser("~/SourceCode/antigravity"),
                         "/Volumes/ThanhSSD/SourceCode/antigravity"):
                f = os.path.join(base, "secrets.env") if base else ""
                if f and os.path.isfile(f):
                    for line in open(f, encoding="utf-8"):
                        if line.startswith("GITHUB_PAT_TOKEN="):
                            tok = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                if tok:
                    break
        req = _u.Request(
            "https://raw.githubusercontent.com/conmangangqua/apps-status/data/snapshot.json",
            headers={"Authorization": f"token {tok}"} if tok else {})
        snap = _json.loads(_u.urlopen(req, timeout=60).read())
        for p in snap.get("partners", []):
            key = (p.get("slug") or "").lower().replace(" ", "_").replace("-", "_")
            if key in ("no_channel", ""):
                continue
            if key == "adc_media":
                key = "adc"
            for a in (p.get("apps") or []):
                ga = ((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}
                for nm in (a.get("slug"), a.get("name"), ga.get("property_name")):
                    if nm:
                        _SNAP_PARTNER[_norm_app(nm)] = key
    except Exception:
        pass
    return _SNAP_PARTNER


def _norm_app(s: str) -> str:
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _get_partner(app_name: str) -> str:
    if app_name in PARTNER_MAP:
        return PARTNER_MAP[app_name]
    # Nguồn chân lý: snapshot apps-status. Thử cả tên gốc và tên bỏ hậu tố "-tmt"/"-prod"
    # (GA property hay gắn thêm) trước khi rơi xuống đoán prefix.
    smap = _snapshot_partner_map()
    n = _norm_app(app_name)
    for cand in (n, n.removesuffix("tmt"), n.removesuffix("prod")):
        if cand and cand in smap:
            return smap[cand]
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
    if "one tabb" in low or "one-tabb" in low or (low.startswith("p") and len(low) > 1 and low[1].isdigit()):
        return "one_tabb"
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
    """📈 +12.3% / 📉 -8.1% / 🆕 khi nền kỳ trước < $1 (so % với nền ~0 vô nghĩa)."""
    if prev < 1:
        return "🆕" if cur > 0 else ""
    pct = (cur - prev) / prev * 100
    if abs(pct) > 999:
        return f"{'📈' if pct >= 0 else '📉'} {'+' if pct >= 0 else '-'}>999%"
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


def _build_revenue_fields(apps_data: list, prev_total: Optional[float],
                          mtd_by_pid: Optional[dict] = None) -> list:
    """v7 (Sếp 2026-08-29: "Hiện đúng tên và cả logo app ra"): mỗi partner 1 khối,
    mỗi app 1 dòng có LOGO + tên thật + tiền + %Δ.

    Vì sao bỏ khối ```ansi``` dùng từ v6.5: emoji KHÔNG render bên trong code
    block, mà logo app chính là emoji server (Discord không cho gắn ảnh vào từng
    dòng của embed field — xem app_emojis.py). Đổi lại: mất căn cột monospace và
    màu ANSI, được logo + tên. Số tiền bọc `inline code` để vẫn nổi thành cột.
    """
    fields = []
    total = sum(a["revenue"] for a in apps_data)

    # Gom app theo partner
    groups = {}
    for a in apps_data:
        groups.setdefault(_get_partner(a["app_name"]), []).append(a)

    order = sorted(groups.items(),
                   key=lambda kv: -sum(a["revenue"] for a in kv[1]))

    # Gom TRƯỚC danh sách app sắp hiện rồi xin logo một lượt — tránh gọi
    # Discord API rải rác trong vòng lặp dựng text.
    show = []
    for p, apps in order:
        if sum(a["revenue"] for a in apps) < 0.01:
            continue
        for a in sorted(apps, key=lambda x: -x["revenue"])[:TOP_PER_PARTNER]:
            if a["revenue"] >= 0.01:
                show.append({"app_name": a["app_name"],
                             "property_id": a.get("property_id")})
    emo = {}
    try:
        import app_emojis
        emo = app_emojis.ensure_emojis(show)
    except Exception as e:                    # logo hỏng KHÔNG được giết báo cáo
        print(f"   ⚠️  bỏ qua logo app: {str(e)[:70]}")

    for p, apps in order:
        p_total = sum(a["revenue"] for a in apps)
        if p_total < 0.01:   # khớp ngưỡng web → hiện ĐỦ mọi đối tác (kể cả One Tabb nhỏ)
            continue
        p_prev = sum(a.get("prev_revenue", 0) for a in apps)
        meta = PARTNER_DISPLAY.get(p, {"label": p.upper(), "emoji": "📦"})
        name = f"{meta['emoji']}  {meta['label']}"

        p_pct = "new" if p_prev <= 0 else f"{(p_total - p_prev) / p_prev * 100:+.1f}%"
        p_ico = "🟢" if p_total >= p_prev else "🔴"
        # Sếp 2026-08-29: "Các đối tác cũng hiện tháng này, hôm nay, hôm qua"
        # — cùng bộ chỉ số với header tổng, để so partner với toàn fleet không
        # phải nhẩm. MTD cộng từ mtd_by_pid (doanh thu MTD của TỪNG property).
        rows = []
        if mtd_by_pid:
            p_mtd = sum(float(mtd_by_pid.get(str(a.get("property_id")), 0) or 0)
                        for a in apps)
            if p_mtd > 0:
                rows.append(f"**Tháng này** `{_money(p_mtd)}`")
        rows.append(f"**Hôm nay** `{_vnd(p_total)}` {p_ico} {p_pct}")
        if p_prev > 0:
            rows.append(f"**Hôm qua** `{_vnd(p_prev)}`")
        # _share_bar() đã kèm sẵn '%', đừng cộng thêm lần nữa
        if total > 0:
            rows.append(f"`{_share_bar(p_total, total)}` tổng fleet")
        apps = sorted(apps, key=lambda a: -a["revenue"])
        for i, a in enumerate(apps[:TOP_PER_PARTNER]):
            if a["revenue"] < 0.01:
                break
            prev = a.get("prev_revenue", 0)
            ico = "🟢" if a["revenue"] >= prev else "🔴"
            pct = "new" if prev <= 0 else f"{(a['revenue'] - prev) / prev * 100:+.1f}%"
            nm = _short_name(a["app_name"])
            logo = emo.get(a["app_name"], "")
            rows.append(f"{logo} **{nm}** `{_vnd(a['revenue'])}` {ico} {pct}".strip())
        rest = [a for a in apps[TOP_PER_PARTNER:] if a["revenue"] >= 0.01]
        if rest:
            rows.append(f"… +{len(rest)} app khác `{_vnd(sum(a['revenue'] for a in rest))}`")
        value = "\n".join(r for r in rows if r)
        fields.append({"name": name[:256], "value": value[:4096] or "—",
                       "inline": False, "_up": p_total >= p_prev})
    return fields


def _build_header_block(target_date: date, apps_data: list,
                        prev_total: Optional[float], mtd_total: Optional[float]) -> str:
    """Sếp 2026-08-29: "Cái header trên cùng cũng đang lệch style".

    Bản cũ là khối ```ansi``` monospace, trong khi phần partner bên dưới đã đổi
    sang text thường + inline code (bắt buộc, vì emoji-logo không render trong
    code block). Hai nửa một tin mà hai kiểu chữ ⇒ đọc như hai bot khác nhau
    dán vào. Nay dùng chung một quy ước: nhãn text thường, số bọc inline code.
    """
    total = sum(a["revenue"] for a in apps_data)
    n_apps = len([a for a in apps_data if a["revenue"] > 0])
    d_str = target_date.strftime("%d/%m")
    d_prev = (target_date - timedelta(days=1)).strftime("%d/%m")
    lines = []
    if mtd_total:
        lines.append(f"**Tháng này** (01→{d_str})  `{_money(mtd_total)}`")
    lines.append(f"**Hôm nay** ({d_str})  `{_money(total)}`")
    if prev_total and prev_total > 0:
        lines.append(f"**Hôm trước** ({d_prev})  `{_money(prev_total)}`")
        diff = total - prev_total
        ico = "🟢" if diff >= 0 else "🔴"
        sign = "+" if diff >= 0 else "-"
        lines.append(f"**Tăng/giảm**  `{sign}{_vnd(abs(diff))}` {ico} "
                     f"{diff / prev_total * 100:+.1f}%")
    lines.append(f"**App có doanh thu**  `{n_apps}`")
    return "\n".join(lines)


def _build_embeds(target_date: date, apps_data: list,
                  prev_total: Optional[float] = None,
                  mtd_total: Optional[float] = None,
                  mtd_by_pid: Optional[dict] = None) -> list:
    """v7.1 — Sếp 2026-08-29: "Khó nhìn vl ko chia section ra".

    Bản v6 nhét mọi partner vào FIELD của cùng một embed. Hồi đó đọc được là nhờ
    mỗi field là một khối ```ansi``` — chính cái khung xám đó tách section, chứ
    không phải bố cục. Bỏ code block đi (để emoji-logo hiện được) là các partner
    dính liền thành một dải chữ.

    Nay tách MỖI PARTNER MỘT EMBED: Discord tự vẽ vạch màu dọc bên trái từng
    embed ⇒ ranh giới rõ mà không tốn dòng kẻ tự chế. Màu vạch theo tăng/giảm
    của chính partner đó, nên lướt mắt là thấy ai tụt.

    Trần của Discord là 10 embed/tin: 1 header + tối đa 9 partner. Hiện có 8
    partner nên vừa; nếu vượt thì phần dư gộp vào embed cuối, KHÔNG âm thầm mất.
    """
    total = sum(a["revenue"] for a in apps_data)
    up = prev_total is None or total >= prev_total
    head = {
        "title": f"💹 Tranquil Revenue — {_day_name_vn(target_date)}, {target_date.strftime('%d/%m/%Y')}",
        "url": "https://admob-revenue-bot.vercel.app/",
        "description": _build_header_block(target_date, apps_data, prev_total, mtd_total),
        "color": 0x10B981 if up else 0xEF4444,
    }
    embeds = [head]
    parts = _build_revenue_fields(apps_data, prev_total, mtd_by_pid)
    MAX_EXTRA = 9
    for f in parts[:MAX_EXTRA]:
        embeds.append({
            "title": f["name"],
            "description": f["value"],
            "color": 0x10B981 if f.get("_up", True) else 0xEF4444,
        })
    if len(parts) > MAX_EXTRA:
        # Thà dồn vào embed cuối còn hơn nuốt mất partner (trần 10 embed của Discord)
        extra = "\n\n".join(f"**{f['name']}**\n{f['value']}" for f in parts[MAX_EXTRA:])
        embeds[-1]["description"] += "\n\n" + extra
    embeds[-1]["footer"] = {"text": "🤖 v7.1 · GA4 Data API (service account)"}
    embeds[-1]["timestamp"] = f"{target_date.isoformat()}T01:00:00Z"
    embeds[-1]["description"] += (
        "\n\n🔗 [Chi tiết từng app trên Web App](https://admob-revenue-bot.vercel.app/)")
    return embeds


# ---------- Public API (compat with main.py) ----------
def send_revenue_report(
    webhook_url: str,
    apps_data=None,
    report_date: Optional[date] = None,
    prev_total: Optional[float] = None,
    mtd_total: Optional[float] = None,
    mtd_by_pid: Optional[dict] = None,
    api_url: str = API_URL,   # giữ tham số cho tương thích — không dùng nữa
) -> bool:
    """Gửi report doanh thu build 100% từ apps_data (GA4 bot vừa quét)."""
    if report_date is None:
        report_date = date.today() - timedelta(days=1)
    if not apps_data:
        print("   ❌ Không có apps_data — bỏ qua gửi Discord.")
        return False

    embeds = _build_embeds(report_date, apps_data, prev_total=prev_total,
                           mtd_total=mtd_total, mtd_by_pid=mtd_by_pid)
    payload = {"username": "Tranquil Revenue Bot", "embeds": embeds}

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
