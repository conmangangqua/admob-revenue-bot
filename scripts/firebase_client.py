"""
firebase_client.py  (v3 - Firebase Management API)
Fetch ad revenue tất cả Firebase project qua:
  1. Firebase Management API  → list TẤT CẢ project (kể cả dự án chưa link GA4 qua Admin API)
  2. Firebase Analytics Details API → lấy GA4 property ID của từng project
  3. GA4 Analytics Data API → query totalAdRevenue per property / per ngày
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

FIREBASE_API  = "https://firebase.googleapis.com/v1beta1"
GA4_DATA_API  = "https://analyticsdata.googleapis.com/v1beta"


# ────────────────────────── helpers ──────────────────────────

def _get(url: str, access_token: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {access_token}"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"   ⚠️  GET error {e.code}: {body[:200]}")
        return {}


def _clean_app_name(raw: str) -> str:
    """
    Làm đẹp tên app từ displayName hoặc projectId của Firebase.
    'quicksave-6c590'  → 'Quicksave'
    'B087 - Gba'       → 'B087 - Gba'  (giữ nguyên nếu đã đẹp)
    """
    # Nếu tên đã có chữ hoa hoặc khoảng trắng → giữ nguyên
    if " " in raw or any(c.isupper() for c in raw):
        return raw.strip()
    # Xóa hash suffix ở cuối: -[a-z0-9]{4,6}
    name = re.sub(r"-[a-z0-9]{4,6}$", "", raw)
    return " ".join(w.capitalize() for w in name.replace("-", " ").split())


# ───────────────────── Firebase project list ─────────────────

def list_firebase_projects(access_token: str) -> list[dict]:
    """
    Dùng Firebase Management API để lấy TẤT CẢ Firebase projects.
    Mỗi project trả về {display_name, project_id, ga4_property_id}.
    Chỉ giữ lại project đã link GA4 (có analyticsDetails).
    """
    projects = []
    page_token = None
    page_num = 0

    # Bước 1: list tất cả project
    raw_projects = []
    while True:
        page_num += 1
        url = f"{FIREBASE_API}/projects?pageSize=100"
        if page_token:
            url += f"&pageToken={page_token}"
        result = _get(url, access_token)
        batch = result.get("results", [])
        raw_projects.extend(batch)
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"   📦 Tìm thấy {len(raw_projects)} Firebase project(s) (qua {page_num} page)")

    # Bước 2: với mỗi project, lấy GA4 property ID
    for p in raw_projects:
        pid = p.get("projectId", "")
        display_raw = p.get("displayName") or pid
        display_name = _clean_app_name(display_raw)

        details = _get(f"{FIREBASE_API}/projects/{pid}/analyticsDetails", access_token)
        prop = details.get("analyticsProperty", {})
        ga4_id = prop.get("id", "")          # dạng "properties/522272427"
        ga4_numeric = ga4_id.replace("properties/", "")

        if not ga4_numeric:
            print(f"   ⏭  {display_name}: chưa link GA4 → bỏ qua")
            continue

        projects.append({
            "display_name": display_name,
            "project_id": pid,
            "ga4_property_id": ga4_numeric,
        })

    print(f"   ✅ {len(projects)}/{len(raw_projects)} project đã link GA4")
    return projects


# ─────────────────────── GA4 revenue query ───────────────────

def get_project_revenue(
    access_token: str, property_id: str, report_date: date
) -> tuple[float, float, int]:
    """
    Query GA4 Data API → totalAdRevenue cho 1 property / 1 ngày.
    Trả về (revenue_usd, ecpm, impressions).
    """
    url = f"{GA4_DATA_API}/properties/{property_id}:runReport"
    date_str = report_date.strftime("%Y-%m-%d")

    payload = json.dumps({
        "dateRanges": [{"startDate": date_str, "endDate": date_str}],
        "metrics": [
            {"name": "totalAdRevenue"},
            {"name": "publisherAdImpressions"},
        ],
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"   ⚠️  Revenue query failed [{e.code}]: {body[:150]}")
        return 0.0, 0.0, 0

    rows = result.get("rows", [])
    if not rows:
        return 0.0, 0.0, 0

    try:
        vals = rows[0]["metricValues"]
        revenue     = float(vals[0]["value"])
        impressions = int(float(vals[1]["value"]))
        ecpm = (revenue / impressions * 1000) if impressions > 0 else 0.0
        return revenue, ecpm, impressions
    except (KeyError, IndexError, ValueError):
        return 0.0, 0.0, 0


# ───────────────────── main entry point ──────────────────────

def get_all_projects_revenue(
    access_token: str, report_date: date
) -> list[dict]:
    """
    Lấy revenue của TẤT CẢ Firebase projects đã link GA4 cho 1 ngày.
    """
    projects = list_firebase_projects(access_token)
    results = []

    for proj in projects:
        name = proj["display_name"]
        ga4_id = proj["ga4_property_id"]

        revenue, ecpm, impressions = get_project_revenue(
            access_token, ga4_id, report_date
        )
        print(f"   💰 {name}: ${revenue:.2f}  eCPM ${ecpm:.2f}  👁 {impressions:,}")

        results.append({
            "app_name": name,
            "project_id": proj["project_id"],
            "revenue": revenue,
            "impressions": impressions,
            "ecpm": ecpm,
        })

    revenue_projects = [r for r in results if r["revenue"] > 0]
    print(f"\n   ✅ {len(revenue_projects)}/{len(results)} projects có revenue")
    return results
