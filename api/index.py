from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.firebase_client import get_all_projects_revenue

def get_access_token_local(client_id: str, client_secret: str, refresh_token: str) -> str:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Cấu hình Headers (CORS và Catching)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        # Cache 60s trên serverless edge, sau đó stale 120s
        self.send_header('Cache-Control', 's-maxage=60, stale-while-revalidate=120')
        self.end_headers()

        # Bước 1: Trích xuất lịch sử từ File tĩnh
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        history_file = os.path.join(base_dir, "data", "revenue_history.json")
        history_data = {}
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
            except Exception:
                pass

        # Bước 2: Bốc số Realtime "Nóng" từ GA4 cho hôm nay
        client_id = os.environ.get("ADMOB_CLIENT_ID", "")
        client_secret = os.environ.get("ADMOB_CLIENT_SECRET", "")
        refresh_token = os.environ.get("ADMOB_REFRESH_TOKEN", "")

        today = date.today()
        # Fallback date_str dùng múi giờ cơ bản
        date_str = today.strftime("%Y-%m-%d")

        if client_id and client_secret and refresh_token:
            try:
                access_token = get_access_token_local(client_id, client_secret, refresh_token)
                apps_today = get_all_projects_revenue(access_token, today)
                
                total_rev = sum(app["revenue"] for app in apps_today)
                
                # Gộp doanh thu hôm nay vào History Dictionary (không ghi đè để giữ các app external từ CSV)
                if date_str not in history_data:
                    history_data[date_str] = {"total": 0, "apps": []}
                
                existing_apps = history_data[date_str].get("apps", [])
                existing_app_dict = {a["name"]: a for a in existing_apps}
                
                for app in apps_today:
                    if app["revenue"] <= 0: continue
                    name = app["app_name"]
                    if name in existing_app_dict:
                        existing_app_dict[name]["rev"] = round(app["revenue"], 2)
                        existing_app_dict[name]["imp"] = app["impressions"]
                        existing_app_dict[name]["ecpm"] = round(app["ecpm"], 2)
                    else:
                        existing_app_dict[name] = {
                            "name": name,
                            "rev": round(app["revenue"], 2),
                            "imp": app["impressions"],
                            "ecpm": round(app["ecpm"], 2)
                        }
                        
                history_data[date_str]["apps"] = list(existing_app_dict.values())
                # Tính lại Total
                history_data[date_str]["total"] = round(sum(a.get("rev", 0) for a in history_data[date_str]["apps"]), 2)
            except Exception as e:
                # Nếu API lỗi, bỏ qua và trả về dữ liệu lịch sử an toàn
                print(f"Error fetching live data: {e}")

        # Bước 3: Nạp thêm thông tin nâng cao từ Google Sheets cho app Quicksave
        from scripts.sheet_reader import get_sheet_data_for_app, get_lunaai_sheet_data
        quicksave_sheet_data = get_sheet_data_for_app("Quicksave")

        if quicksave_sheet_data:
            for d_str, day_info in history_data.items():
                if d_str in quicksave_sheet_data:
                    q_data = quicksave_sheet_data[d_str]
                    if "apps" in day_info:
                        for app in day_info["apps"]:
                            target_name = app["name"].strip().lower()
                            if 'quicksave' in target_name:
                                app["sheet_data"] = q_data
                                
                                # Ghi đè doanh thu từ Google Sheets
                                if 'total_rev_vnd' in q_data:
                                    try:
                                        total_rev_vnd_val = float(str(q_data['total_rev_vnd']).replace(',', '').strip())
                                        if total_rev_vnd_val > 0:
                                            real_vnd = total_rev_vnd_val * 1000000
                                            rev_usd = real_vnd / 25400.0
                                            old_rev = app.get("rev", 0)
                                            app["rev"] = round(rev_usd, 2)
                                            if "total" in day_info:
                                                day_info["total"] = round(day_info["total"] - old_rev + rev_usd, 2)
                                    except Exception:
                                        pass

        # Bước 3b: Nạp thêm thông tin từ Google Sheets cho app LunaAI Chat
        try:
            lunaai_data = get_lunaai_sheet_data()
            if lunaai_data:
                LUNAAI_NAME = "LunaAi-Chat"  # Khớp chính xác tên từ GA4
                for d_str, day_info in history_data.items():
                    if d_str not in lunaai_data:
                        continue
                    l = lunaai_data[d_str]
                    rev_usd = l.get("revenue_usd", 0.0)
                    cost_usd = l.get("cost_usd", 0.0)
                    profit_usd = l.get("profit_usd", 0.0)

                    if rev_usd == 0:
                        continue

                    # Quy đổi sang triệu VND
                    VND_RATE = 25400.0
                    rev_vnd_mil    = (rev_usd    * VND_RATE) / 1_000_000
                    cost_vnd_mil   = (cost_usd   * VND_RATE) / 1_000_000
                    profit_vnd_mil = (profit_usd * VND_RATE) / 1_000_000
                    profit_pct = round((profit_usd / rev_usd) * 100) if rev_usd > 0 else 0

                    luna_sheet = {
                        "total_rev_vnd": str(round(rev_vnd_mil, 3)),
                        "cost_vnd":      str(round(cost_vnd_mil, 3)),
                        "marketing_profit_vnd": str(round(profit_vnd_mil, 3)),
                        "profit_pct_sheet": f"{profit_pct}%"
                    }

                    if "apps" not in day_info:
                        day_info["apps"] = []

                    # Kiểm tra app này đã có chưa
                    existing = next((a for a in day_info["apps"] if a["name"] == LUNAAI_NAME), None)
                    if existing:
                        existing["sheet_data"] = luna_sheet
                        old_rev = existing.get("rev", 0)
                        existing["rev"] = round(rev_usd, 2)
                        if "total" in day_info:
                            day_info["total"] = round(day_info["total"] - old_rev + rev_usd, 2)
                    else:
                        day_info["apps"].append({
                            "name": LUNAAI_NAME,
                            "rev": round(rev_usd, 2),
                            "imp": 0,
                            "ecpm": 0,
                            "sheet_data": luna_sheet
                        })
                        if "total" in day_info:
                            day_info["total"] = round(day_info["total"] + rev_usd, 2)
        except Exception as e:
            print(f"Error fetching LunaAI sheet data: {e}")

        # Sắp xếp lại log theo ngày giảm dần chuẩn format Chart
        sorted_history = dict(sorted(history_data.items(), reverse=True))

        # Trả cục JSON gộp (Hybrid Data)
        self.wfile.write(json.dumps(sorted_history).encode('utf-8'))
        return

