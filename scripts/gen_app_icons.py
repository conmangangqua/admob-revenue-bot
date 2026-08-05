#!/usr/bin/env python3
"""gen_app_icons.py — sinh data/app_icons.json = { "<tên app GA>": "<icon_url>" }.

Dashboard (index.html) chỉ có tên app + revenue, KHÔNG có icon. Script này map:
  apps-status snapshot: app.firebase.meta.ga4.property_id  +  app.store_info.icon_url
  → property_id → icon_url
rồi qua data/ga_names.json (property_id → tên hiển thị GA) → { tên: icon_url }.

Chạy trong daily job (main.py) để icon luôn tươi. Nguồn snapshot = GitHub apps-status@data.
"""
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NAMES = os.path.join(REPO, "public", "data", "ga_names.json")
OUT = os.path.join(REPO, "public", "data", "app_icons.json")
SNAP_URL = "https://raw.githubusercontent.com/conmangangqua/apps-status/data/snapshot.json"


def _fetch_snapshot():
    tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    headers = {"User-Agent": "gen-app-icons/1.0"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(SNAP_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


_PARTNER_PFX = ("herond", "bbl", "bll", "ntech", "affica", "adc media", "adc",
                "azura", "one tabb", "one-tabb")


# App mà GA gọi một tên, hub gọi tên khác — không suy ra được bằng prefix/fuzzy, và snapshot
# cũng thiếu ga4.property_id để bắc cầu. Map tay: {canonical tên GA: canonical slug hub}.
# Thêm dòng mới khi thấy app nào trên dashboard hiện trần không logo.
_ALIAS = {
    "wifipasswordmap": "wifikeymap",     # GA "BBL WiFi Password Map" ↔ hub "Wifi Key Map"
}


def _norm(s):
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _strip_prefix(name):
    low = (name or "").lower().strip()
    import re
    low = re.sub(r"^(apb|b|p)\d+\s*[-–]?\s*", "", low)   # bỏ mã B117/APB972/P01…
    # Tên GA property hay ở dạng slug gạch nối ("adc-media-jade-browser"): đổi -/_ thành
    # space thì mới cắt được prefix đối tác, nếu không sẽ giữ nguyên cả cụm rồi trượt khớp
    # icon (Sếp 2026-08-05: jade-browser / snapsaver / reveriedrama mất logo trên web).
    low = low.replace("-", " ").replace("_", " ")
    low = re.sub(r"\s+", " ", low).strip()
    for pfx in _PARTNER_PFX:
        if low.startswith(pfx + " "):
            return low[len(pfx) + 1:].strip()
    return low


def build():
    snap = _fetch_snapshot()
    # Icon ưu tiên: store_info.icon_url (Play/App Store) → a.icon (icon hub/repo — apps-status
    # render field này khi chưa có store icon; QuickSave/FluxVPN… nằm ở đây).
    pid_icon, slug_icon = {}, {}
    for p in snap.get("partners", []):
        for a in p.get("apps", []):
            icon = (a.get("store_info") or {}).get("icon_url") or a.get("icon")
            if not icon:
                continue
            pid = (((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}).get("property_id")
            if pid:
                pid_icon[str(pid)] = icon
            # index phụ theo slug + tên (bắt app có icon nhưng ga4.property_id=None, vd SnapVid)
            for key in (a.get("slug"), _strip_prefix(a.get("name"))):
                k = _norm(key)
                if k:
                    slug_icon.setdefault(k, icon)
    names = json.load(open(NAMES, encoding="utf-8")) if os.path.isfile(NAMES) else {}
    long_keys = [(k, ic) for k, ic in slug_icon.items() if len(k) >= 6]

    def _fuzzy(nn):
        # prefix 2 chiều (vd slug 'genifyai' ⊂ 'genifyaigenarator' — app đổi tên/GA property)
        for k, ic in long_keys:
            if nn.startswith(k) or k.startswith(nn):
                return ic
        return None

    out = 0
    result = {}
    for pid, name in names.items():
        if not name:
            continue
        nn = _norm(_strip_prefix(name))
        icon = (pid_icon.get(str(pid)) or slug_icon.get(nn)
                or slug_icon.get(_ALIAS.get(nn, "")) or _fuzzy(nn))
        if icon:
            result[name] = icon          # key tên hiển thị (khớp cũ)
            if nn:
                result[nn] = icon        # key CANONICAL (norm+strip prefix) → frontend tra theo canon,
                                          # miễn nhiễm khác case/space/prefix ('Herond SnapVid' vs 'Herond Snapvid')
            out += 1
    # ── Bổ sung: app CÓ doanh thu nhưng KHÔNG nằm trong ga_names.json ────────────────
    # build() chỉ duyệt `names` nên app mới (GA property chưa map tên) không bao giờ được
    # gán icon — web hiện tên slug trần, không logo. Quét thẳng tên trong revenue_history
    # rồi khớp bằng slug/fuzzy như trên.
    try:
        hist_path = os.path.join(REPO, "public", "data", "revenue_history.json")
        hist = json.load(open(hist_path, encoding="utf-8"))
        seen = set()
        for day in sorted(hist)[-30:]:
            for a in (hist[day].get("apps") or []):
                nm = a.get("name")
                if not nm or nm in result or nm in seen:
                    continue
                seen.add(nm)
                nn = _norm(_strip_prefix(nm))
                icon = slug_icon.get(nn) or slug_icon.get(_ALIAS.get(nn, "")) or _fuzzy(nn)
                if icon:
                    result[nm] = icon
                    if nn:
                        result.setdefault(nn, icon)
                    out += 1
    except Exception as e:
        print(f"[gen_app_icons] bỏ qua bước quét history: {e}")

    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[gen_app_icons] {out}/{len(names)} app có icon → {OUT}")
    return result


if __name__ == "__main__":
    build()
