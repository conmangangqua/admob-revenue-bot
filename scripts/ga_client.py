"""
ga_client.py — Đọc doanh thu ads qua GA4 Data API bằng service account hub-admin-sa.

Thay thế hoàn toàn firebase_client.py cũ (user refresh-token + fallback tạo temp key
firebase-adminsdk — fallback đó vô dụng vì SA adminsdk không nằm trong GA ACL,
hậu quả bot under-report: ~$500/ngày trong khi số thật ~$2.5K/ngày).

Kiến trúc mới (2026-07-27):
  1. Analytics Admin API `accountSummaries` → tự discover MỌI property SA đọc được
     (SA đã được add Viewer cấp account: 384588955 / 385925354 / 394293629 / ...).
     App mới link GA vào các account này sẽ TỰ xuất hiện, không cần sửa code.
  2. GA4 Data API `runReport` per property: totalAdRevenue + publisherAdImpressions.
  3. Tên app: ưu tiên data/ga_names.json (map property → displayName Firebase,
     giữ liên tục naming với history cũ), fallback displayName của GA property.

Auth (thứ tự ưu tiên):
  1. ENV HUB_ADMIN_SA_KEY  — nội dung JSON key (GitHub Actions secret)
  2. ENV HUB_ADMIN_KEY_PATH hoặc ~/.config/gcloud/hub-admin-sa.json — file key
  3. gcloud impersonation (máy local đã `gcloud auth login`, cần TokenCreator trên SA)
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import List, Optional

GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"
GA4_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
SA_EMAIL = "hub-admin-sa@apps-status-reader.iam.gserviceaccount.com"
DEFAULT_KEY_PATH = os.path.expanduser("~/.config/gcloud/hub-admin-sa.json")
NAMES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "data", "ga_names.json"
)
HTTP_TIMEOUT = 30


# ─────────────────────────── auth ───────────────────────────

def _token_from_key_info(info: dict) -> str:
    from google.oauth2 import service_account
    import google.auth.transport.requests
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=[GA4_SCOPE]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def get_ga_token() -> str:
    """Lấy access-token SA scope analytics.readonly theo chuỗi ưu tiên."""
    key_env = os.environ.get("HUB_ADMIN_SA_KEY", "").strip()
    if key_env:
        print("   🔑 Auth: SA key từ ENV HUB_ADMIN_SA_KEY")
        return _token_from_key_info(json.loads(key_env))

    key_path = os.environ.get("HUB_ADMIN_KEY_PATH", "") or DEFAULT_KEY_PATH
    if os.path.exists(key_path):
        print(f"   🔑 Auth: SA key file {key_path}")
        with open(key_path) as f:
            return _token_from_key_info(json.load(f))

    # Local fallback: impersonation qua gcloud (không cần key file)
    out = subprocess.run(
        ["gcloud", "auth", "print-access-token",
         f"--impersonate-service-account={SA_EMAIL}", f"--scopes={GA4_SCOPE}"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode == 0 and out.stdout.strip():
        print("   🔑 Auth: gcloud impersonation → " + SA_EMAIL)
        return out.stdout.strip()
    raise RuntimeError(
        "Không lấy được token SA: thiếu HUB_ADMIN_SA_KEY / key file, "
        "và impersonation fail: " + out.stderr[-300:]
    )


# ─────────────────────── HTTP helpers ───────────────────────

def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read())


def _post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return json.loads(r.read())


# ─────────────────── property discovery ─────────────────────

import re
# GA4 property DEV (build test vẫn thu ít ad revenue) → loại, tránh trùng dòng với prod
# trên dashboard (Sếp 2026-07-27: "Onyx Browser" x2 = onyx-browser-90060 + onyx-browser-dev).
# Bắt: '...-dev', '...-dev-789', 'goalarenadev', '...dev$'. App prod luôn có property riêng.


def _is_dev_property(display: str) -> bool:
    d = (display or "").strip().lower()
    return bool(re.search(r"[-_ ]dev(?:[-_ ]|\d|$)|dev$", d))


def list_properties(token: str, include_dev: bool = False) -> List[dict]:
    """Mọi GA4 property SA đọc được: [{property_id, display, account}].
    Mặc định LOẠI property -dev (build test) để không trùng dòng với prod."""
    props, page = [], ""
    while True:
        url = f"{GA4_ADMIN_API}/accountSummaries?pageSize=200"
        if page:
            url += f"&pageToken={page}"
        data = _get(url, token)
        for acc in data.get("accountSummaries", []):
            acc_id = acc.get("account", "").split("/")[-1]
            for p in acc.get("propertySummaries", []):
                disp = p.get("displayName", "")
                if not include_dev and _is_dev_property(disp):
                    continue
                props.append({
                    "property_id": p["property"].split("/")[-1],
                    "display": disp,
                    "account": acc_id,
                })
        page = data.get("nextPageToken", "")
        if not page:
            break
    return props


SNAPSHOT_URL = ("https://raw.githubusercontent.com/conmangangqua/"
                "apps-status/data/snapshot.json")


def _names_from_snapshot() -> dict:
    """{property_id: tên app THẬT} lấy từ snapshot apps-status.

    🔴 Sếp bắt 2026-08-29: báo cáo doanh thu hiện `chapture-tmt`, `cliffy-tmt`,
    `affica-plotwist` — tức tên PROJECT FIREBASE, không phải tên app. Nguyên nhân:
    `ga_names.json` là file tĩnh phải bổ sung TAY, mà fleet thì cứ đẻ thêm app;
    property nào chưa kịp thêm thì rơi về `displayName` của GA property, và người
    ta đặt tên property theo project.

    Tệ hơn tên xấu: có cái SAI HẲN. `cliffy-tmt` thật ra là app **Dramelo** — app
    đã đổi tên nhưng project giữ tên cũ, nên báo cáo gọi tên một app không còn tồn
    tại. Kiểu lỗi này không bao giờ tự hết nếu vẫn trông vào việc nhớ sửa tay.

    Nên bù tự động từ snapshot (nguồn đang dùng cho icon dashboard, cùng khoá
    `firebase.meta.ga4.property_id`). Lỗi mạng thì trả {} — mất tên đẹp, KHÔNG
    làm chết báo cáo.
    """
    tok = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    req = urllib.request.Request(SNAPSHOT_URL)
    if tok:
        req.add_header("Authorization", f"token {tok}")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            snap = json.load(r)
    except Exception as e:
        print(f"   ⚠️  không đọc được snapshot để lấy tên app ({e}) — dùng tên GA")
        return {}
    out = {}
    for part in snap.get("partners", []):
        for a in part.get("apps", []):
            ga = ((a.get("firebase") or {}).get("meta") or {}).get("ga4") or {}
            pid = str(ga.get("property_id") or "")
            nm = (a.get("name") or "").strip()
            if pid and nm:
                out[pid] = nm
    return out


def _load_name_overrides() -> dict:
    """File tĩnh THẮNG, snapshot chỉ BÙ cho property chưa có tên.

    Cố ý không để snapshot ghi đè: `app_name` là KHOÁ của lịch sử doanh thu và
    của phép so hôm-trước. Đổi tên hàng loạt 59 app đang chạy đúng sẽ làm mọi %Δ
    thành "new" và cắt đứt biểu đồ lịch sử — sửa cái đang đẹp thành cái đang hỏng.
    """
    file_names = {}
    try:
        with open(NAMES_FILE, encoding="utf-8") as f:
            file_names = json.load(f)
    except Exception:
        pass
    merged = dict(_names_from_snapshot())
    merged.update(file_names)        # file đè snapshot
    return merged


# ─────────────────────── revenue query ──────────────────────

def _run_report(token: str, property_id: str, date_str: str, end_str: str = None):
    result = _post(
        f"{GA4_DATA_API}/properties/{property_id}:runReport", token,
        {
            "dateRanges": [{"startDate": date_str, "endDate": end_str or date_str}],
            "metrics": [{"name": "totalAdRevenue"},
                        {"name": "publisherAdImpressions"}],
        },
    )
    rows = result.get("rows", [])
    if not rows:
        return 0.0, 0.0, 0
    vals = rows[0]["metricValues"]
    revenue = float(vals[0]["value"])
    impressions = int(float(vals[1]["value"]))
    ecpm = (revenue / impressions * 1000) if impressions > 0 else 0.0
    return revenue, ecpm, impressions


def get_total_revenue(token: str, start_date: date, end_date: date) -> float:
    """Tổng doanh thu ads MỌI property trong khoảng ngày (1 runReport range/property).
    Dùng cho MTD — không lấy từ history vì các ngày thời bot cũ bị thiếu số."""
    props = list_properties(token)
    s, e = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    def fetch(p):
        try:
            rev, _, _ = _run_report(token, p["property_id"], s, e)
            return rev
        except Exception:
            return 0.0

    with ThreadPoolExecutor(max_workers=10) as ex:
        return sum(ex.map(fetch, props))


def get_all_revenue(token: str, report_date: date) -> List[dict]:
    """Doanh thu 1 ngày của TẤT CẢ property SA đọc được.
    Trả về list {app_name, revenue, impressions, ecpm} — sorted desc theo revenue."""
    date_str = report_date.strftime("%Y-%m-%d")
    props = list_properties(token)
    if not props:
        raise RuntimeError(
            "accountSummaries trả về RỖNG — SA chưa được add vào GA account nào "
            "(hoặc quyền bị thu hồi). Kiểm tra Account Access Management."
        )
    names = _load_name_overrides()
    print(f"   🔎 {len(props)} property khả dụng, query ngày {date_str}…")

    def fetch(p: dict) -> Optional[dict]:
        try:
            rev, ecpm, imp = _run_report(token, p["property_id"], date_str)
            return {
                "app_name": names.get(p["property_id"]) or p["display"] or p["property_id"],
                # Khoá ỔN ĐỊNH để tra logo/icon. Tên app thì đổi (app rebrand,
                # property đặt theo project cũ) nên tra icon theo tên là trượt —
                # đúng lý do logo không hiện được trước đây.
                "property_id": p["property_id"],
                "revenue": rev,
                "impressions": imp,
                "ecpm": ecpm,
            }
        except urllib.error.HTTPError as e:
            print(f"   ⚠️  {p['display'] or p['property_id']}: HTTP {e.code}")
            return None
        except Exception as e:
            print(f"   ⚠️  {p['display'] or p['property_id']}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = [r for r in ex.map(fetch, props) if r is not None]

    results.sort(key=lambda a: -a["revenue"])
    total = sum(a["revenue"] for a in results)
    print(f"   ✅ {len(results)}/{len(props)} property OK — tổng ${total:,.2f}")
    return results
