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
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NAMES = os.path.join(REPO, "data", "ga_names.json")
OUT = os.path.join(REPO, "data", "app_icons.json")
SNAP_URL = "https://raw.githubusercontent.com/conmangangqua/apps-status/data/snapshot.json"


def _fetch_snapshot():
    tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    headers = {"User-Agent": "gen-app-icons/1.0"}
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(SNAP_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def _scrape_play_icon(bundle):
    """Fallback: lấy icon play-lh trực tiếp từ Play listing khi apps-status chưa có icon_url."""
    if not bundle:
        return None
    url = f"https://play.google.com/store/apps/details?id={bundle}&hl=en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
        m = re.search(r'https://play-lh\.googleusercontent\.com/[\w\-]+', html)
        return m.group(0) if m else None
    except Exception:
        return None


def build():
    snap = _fetch_snapshot()
    pid_icon, pid_bundle = {}, {}
    for p in snap.get("partners", []):
        for a in p.get("apps", []):
            si = a.get("store_info") or {}
            pid = (((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}).get("property_id")
            if not pid:
                continue
            pid = str(pid)
            if si.get("icon_url"):
                pid_icon[pid] = si["icon_url"]
            elif a.get("bundle_id"):
                pid_bundle[pid] = a["bundle_id"]   # có app + bundle nhưng thiếu icon → scrape sau
    names = json.load(open(NAMES, encoding="utf-8")) if os.path.isfile(NAMES) else {}
    out, scraped = {}, 0
    for pid, name in names.items():
        if not name:
            continue
        pid = str(pid)
        icon = pid_icon.get(pid)
        if not icon and pid in pid_bundle:
            icon = _scrape_play_icon(pid_bundle[pid])   # fallback Play scrape
            if icon:
                scraped += 1
        if icon:
            out[name] = icon
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[gen_app_icons] {len(out)}/{len(names)} app có icon "
          f"(snapshot {len(out) - scraped} + scrape Play {scraped}) → {OUT}")
    return out


if __name__ == "__main__":
    build()
