"""
admob_client.py
Wrapper cho AdMob Reporting API v1.
Hỗ trợ: lấy access token, list accounts, fetch network report theo ngày.
"""
import json
import urllib.parse
import urllib.request
from datetime import date
from typing import Optional, List


TOKEN_URL = "https://oauth2.googleapis.com/token"
ADMOB_BASE = "https://admob.googleapis.com/v1"


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Refresh OAuth2 token — dùng mỗi lần chạy."""
    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"   ❌ Token refresh failed [{e.code}]: {error_body}")
        raise RuntimeError(f"OAuth token refresh failed: {error_body}")

    token = result.get("access_token")
    if not token:
        raise RuntimeError(f"Không lấy được access_token: {result}")
    return token


def list_accounts(access_token: str) -> List[dict]:
    """Liệt kê tất cả AdMob publisher accounts của tài khoản Google."""
    req = urllib.request.Request(
        f"{ADMOB_BASE}/accounts",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    accounts = result.get("account", [])
    print(f"   📋 Tìm thấy {len(accounts)} publisher account(s)")
    return accounts


def get_network_report(
    access_token: str,
    publisher_id: str,
    report_date: date,
) -> List[dict]:
    """
    Lấy network report cho 1 publisher account theo ngày.
    Trả về list dict: {app_name, app_id, revenue, impressions, ecpm}
    """
    url = f"{ADMOB_BASE}/accounts/{publisher_id}/networkReport:generate"

    payload = {
        "reportSpec": {
            "dateRange": {
                "startDate": {
                    "year": report_date.year,
                    "month": report_date.month,
                    "day": report_date.day,
                },
                "endDate": {
                    "year": report_date.year,
                    "month": report_date.month,
                    "day": report_date.day,
                },
            },
            "dimensions": ["APP"],
            "metrics": ["ESTIMATED_EARNINGS", "IMPRESSIONS", "IMPRESSION_RPM"],
            "sortConditions": [
                {"metric": "ESTIMATED_EARNINGS", "order": "DESCENDING"}
            ],
            "localizationSettings": {"currencyCode": "USD"},
        }
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

    results = []
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"   ⚠️  AdMob API error [{publisher_id}]: {e.code} - {error_body[:200]}")
        return []

    # AdMob trả về mảng JSON hoặc NDJSON
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            items = [items]
    except json.JSONDecodeError:
        items = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    for item in items:
        if "row" not in item:
            continue
        row = item["row"]
        dim = row.get("dimensionValues", {})
        met = row.get("metricValues", {})

        app_info = dim.get("APP", {})
        app_name = app_info.get("displayLabel") or app_info.get("value", "Unknown App")
        app_id = app_info.get("value", "")

        # ESTIMATED_EARNINGS tính bằng microsValue (1/1,000,000 USD)
        earnings_micro = met.get("ESTIMATED_EARNINGS", {}).get("microsValue", "0")
        revenue = int(earnings_micro) / 1_000_000

        impressions = int(met.get("IMPRESSIONS", {}).get("integerValue", "0"))
        ecpm = float(met.get("IMPRESSION_RPM", {}).get("doubleValue", 0))

        results.append(
            {
                "app_name": app_name,
                "app_id": app_id,
                "revenue": revenue,
                "impressions": impressions,
                "ecpm": ecpm,
            }
        )

    return results
