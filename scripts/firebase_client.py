"""
firebase_client.py  (v4 - Auto Service Account Fallback)
Fetch ad revenue tất cả Firebase project qua:
  1. Firebase Management API  → list TẤT CẢ project
  2. Firebase Analytics Details API → lấy GA4 property ID
  3. GA4 Analytics Data API → query totalAdRevenue (bằng user token)
  Fallback khi GA4 trả 403:
  4. IAM API → tìm firebase-adminsdk SA của project → tạo temp key
  5. Ký JWT bằng RSA private key → đổi lấy GA4 access token (service account)
  6. Retry GA4 query với SA token
  7. Xóa temp key (cleanup)
"""
import base64
import json
import re
import time
import urllib.error
import urllib.parse
from datetime import date
from typing import Optional, List, Tuple

FIREBASE_API = "https://firebase.googleapis.com/v1beta1"
GA4_DATA_API = "https://analyticsdata.googleapis.com/v1beta"
IAM_API      = "https://iam.googleapis.com/v1"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
GA4_SCOPE    = "https://www.googleapis.com/auth/analytics.readonly"


# ─────────────────────────── helpers ─────────────────────────────

def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"   ⚠️  GET {e.code}: {body[:200]}")
        return {}


def _clean_app_name(raw: str) -> str:
    # Strip trailing "-App" / "-app" suffix (thừa trong context revenue report)
    cleaned = re.sub(r'(?i)-app$', '', raw).strip()
    if " " in cleaned or any(c.isupper() for c in cleaned):
        return cleaned
    name = re.sub(r"-[a-z0-9]{4,6}$", "", cleaned)
    return " ".join(w.capitalize() for w in name.replace("-", " ").split())


# ──────────────── Service Account Auto-Key Fallback ──────────────

def _jwt_exchange(key_json: dict, scope: str) -> str:
    """
    Dùng service account JSON để ký JWT và đổi lấy OAuth2 access token.
    Requires: pip install cryptography
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    now = int(time.time())
    header  = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": key_json["client_email"],
        "scope": scope,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    msg = f"{h}.{p}".encode()

    private_key = serialization.load_pem_private_key(
        key_json["private_key"].encode(), password=None
    )
    sig = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    jwt_token = f"{h}.{p}.{_b64url(sig)}"

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def _get_sa_token(user_token: str, project_id: str) -> Optional[str]:
    """
    Tự động:
      1. list service accounts → tìm firebase-adminsdk
      2. POST /keys → tạo temp private key
      3. ký JWT → lấy GA4 access token
      4. DELETE key (cleanup)
    """
    try:
        # 1. Tìm firebase-adminsdk SA
        data = _get(f"{IAM_API}/projects/{project_id}/serviceAccounts", user_token)
        accounts = data.get("accounts", [])
        firebase_sa = next(
            (sa["email"] for sa in accounts if "firebase-adminsdk" in sa.get("email", "")),
            None,
        )
        if not firebase_sa:
            print(f"   ⚠️  Không tìm thấy firebase-adminsdk SA cho {project_id}")
            return None

        # 2. Tạo temp key
        keys_url = f"{IAM_API}/projects/{project_id}/serviceAccounts/{firebase_sa}/keys"
        body = json.dumps({"privateKeyType": "TYPE_GOOGLE_CREDENTIALS_FILE"}).encode()
        req = urllib.request.Request(
            keys_url,
            data=body,
            headers={
                "Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            key_resp = json.loads(r.read())

        key_name = key_resp.get("name", "")
        key_json  = json.loads(base64.b64decode(key_resp["privateKeyData"]).decode())

        # 3. Ký JWT → lấy token
        sa_token = _jwt_exchange(key_json, GA4_SCOPE)

        # 4. Xóa temp key (best-effort)
        if key_name:
            try:
                del_req = urllib.request.Request(
                    f"{IAM_API}/{key_name}",
                    headers={"Authorization": f"Bearer {user_token}"},
                    method="DELETE",
                )
                urllib.request.urlopen(del_req)
            except Exception:
                pass

        return sa_token

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"   ⚠️  SA key creation failed [{e.code}]: {body[:200]}")
        return None
    except Exception as ex:
        print(f"   ⚠️  SA fallback error: {ex}")
        return None


# ───────────────────── Firebase project list ─────────────────────

def list_firebase_projects(access_token: str) -> List[dict]:
    """Dùng Firebase Management API lấy TẤT CẢ project đã link GA4."""
    raw_projects = []
    page_token = None
    page_num = 0

    while True:
        page_num += 1
        url = f"{FIREBASE_API}/projects?pageSize=100"
        if page_token:
            url += f"&pageToken={page_token}"
        result = _get(url, access_token)
        raw_projects.extend(result.get("results", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"   📦 Tìm thấy {len(raw_projects)} Firebase project(s) (qua {page_num} page)")

    projects = []
    for p in raw_projects:
        pid = p.get("projectId", "")
        display_name = _clean_app_name(p.get("displayName") or pid)

        details = _get(f"{FIREBASE_API}/projects/{pid}/analyticsDetails", access_token)
        ga4_id = details.get("analyticsProperty", {}).get("id", "")
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


# ──────────────────────── GA4 revenue query ──────────────────────

def _run_ga4_report(token: str, property_id: str, date_str: str) -> Tuple[float, float, int]:
    url = f"{GA4_DATA_API}/properties/{property_id}:runReport"
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
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())

    rows = result.get("rows", [])
    if not rows:
        return 0.0, 0.0, 0

    vals = rows[0]["metricValues"]
    revenue     = float(vals[0]["value"])
    impressions = int(float(vals[1]["value"]))
    ecpm = (revenue / impressions * 1000) if impressions > 0 else 0.0
    return revenue, ecpm, impressions


def get_project_revenue(
    user_token: str,
    project_id: str,
    property_id: str,
    report_date: date,
) -> Tuple[float, float, int, bool]:
    """
    Lấy revenue cho 1 project/1 ngày.
    Returns: (revenue, ecpm, impressions, has_permission)
    """
    date_str = report_date.strftime("%Y-%m-%d")

    # Lần 1: user token
    try:
        rev, ecpm, imp = _run_ga4_report(user_token, property_id, date_str)
        return rev, ecpm, imp, True
    except urllib.error.HTTPError as e:
        if e.code != 403:
            body = e.read().decode()
            print(f"   ⚠️  GA4 lỗi [{e.code}]: {body[:150]}")
            return 0.0, 0.0, 0, True  # lỗi khác, không phải quyền
        # 403 → thử SA fallback

    print(f"   🔑 403 → SA auto-key fallback [{project_id}]...")
    sa_token = _get_sa_token(user_token, project_id)
    if not sa_token:
        return 0.0, 0.0, 0, False  # không có quyền

    try:
        rev, ecpm, imp = _run_ga4_report(sa_token, property_id, date_str)
        return rev, ecpm, imp, True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"   ❌ SA fallback cũng thất bại [{e.code}]: {body[:150]}")
        return 0.0, 0.0, 0, False  # không có quyền


# ────────────────────────── entry point ──────────────────────────

def get_all_projects_revenue(
    access_token: str, report_date: date
) -> List[dict]:
    """Lấy revenue TẤT CẢ Firebase projects đã link GA4 cho 1 ngày."""
    projects = list_firebase_projects(access_token)
    results  = []

    for proj in projects:
        name   = proj["display_name"]
        ga4_id = proj["ga4_property_id"]
        pid    = proj["project_id"]

        revenue, ecpm, impressions, has_permission = get_project_revenue(
            access_token, pid, ga4_id, report_date
        )
        status = "💰" if has_permission else "🚫"
        print(f"   {status} {name}: ${revenue:.2f}  eCPM ${ecpm:.2f}  👁 {impressions:,}")

        results.append({
            "app_name": name,
            "project_id": pid,
            "revenue": revenue,
            "impressions": impressions,
            "ecpm": ecpm,
            "no_permission": not has_permission,
        })

    revenue_projects = [r for r in results if r["revenue"] > 0]
    blocked_projects = [r for r in results if r["no_permission"]]
    print(f"\n   ✅ {len(revenue_projects)}/{len(results)} projects có revenue")
    if blocked_projects:
        print(f"   🚫 {len(blocked_projects)} projects không có quyền GA4: {[r['app_name'] for r in blocked_projects]}")
    return results
