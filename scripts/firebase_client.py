"""
firebase_client.py
Fetch ad revenue từng Firebase project qua:
  1. Analytics Admin API → list tất cả GA4 properties (bao gồm Firebase projects)
  2. GA4 Analytics Data API → query totalAdRevenue per property
Không cần Firebase Management API!
"""
import json
import urllib.request
import urllib.error
from datetime import date

GA4_ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"
GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"


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


def list_ga4_properties(access_token: str) -> list[dict]:
    """
    Lấy tất cả GA4 properties của tài khoản Google.
    Mỗi Firebase project có linked GA4 property.
    """
    result = _get(f"{GA4_ADMIN_API}/accountSummaries", access_token)
    summaries = result.get("accountSummaries", [])

    properties = []
    for account in summaries:
        for prop in account.get("propertySummaries", []):
            prop_resource = prop.get("property", "")  # "properties/123456789"
            prop_id = prop_resource.replace("properties/", "")
            prop_name = prop.get("displayName", prop_id)
            properties.append({"property_id": prop_id, "display_name": prop_name})

    print(f"   📦 Tìm thấy {len(properties)} GA4 property/Firebase project(s)")
    return properties


def get_project_revenue(
    access_token: str, property_id: str, report_date: date
) -> float:
    """
    Query GA4 Data API lấy totalAdRevenue cho 1 property trong 1 ngày.
    """
    url = f"{GA4_DATA_API}/properties/{property_id}:runReport"
    date_str = report_date.strftime("%Y-%m-%d")

    payload = {
        "dateRanges": [{"startDate": date_str, "endDate": date_str}],
        "metrics": [
            {"name": "totalAdRevenue"},
            {"name": "publisherAdImpressions"},
        ],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
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


import re


def _clean_app_name(raw: str) -> str:
    """
    Làm đẹp tên app từ Firebase project ID.
    "quicksave-6c590" → "Quicksave"
    "video-downloader-1-c34aa" → "Video Downloader 1"
    "lunaai-bb200" → "Lunaai"
    """
    # Xóa hash suffix ở cuối: -[a-z0-9]{4,6}
    name = re.sub(r'-[a-z0-9]{4,6}$', '', raw)
    # Capitalize từng từ
    return ' '.join(w.capitalize() for w in name.replace('-', ' ').split())


def get_all_projects_revenue(
    access_token: str, report_date: date
) -> list[dict]:
    """
    Lấy revenue của tất cả GA4 properties (Firebase projects) cho 1 ngày.
    """
    properties = list_ga4_properties(access_token)
    results = []

    for prop in properties:
        prop_id = prop["property_id"]
        raw_name = prop["display_name"]
        display_name = _clean_app_name(raw_name)

        revenue, ecpm, impressions = get_project_revenue(
            access_token, prop_id, report_date
        )
        print(f"   💰 {display_name}: ${revenue:.2f}  eCPM ${ecpm:.2f}  👁 {impressions:,}")

        results.append({
            "app_name": display_name,
            "project_id": prop_id,
            "revenue": revenue,
            "impressions": impressions,
            "ecpm": ecpm,
        })

    revenue_projects = [r for r in results if r["revenue"] > 0]
    print(f"\n   ✅ {len(revenue_projects)}/{len(results)} projects có revenue")
    return results
