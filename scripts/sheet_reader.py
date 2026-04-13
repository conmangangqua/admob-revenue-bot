import os
import gspread
from google.oauth2.service_account import Credentials
import datetime

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

# Tạm fix cứng ID Google Sheet của ứng dụng Quicksave
# Khi nào cần app khác, có thể tự động đọc cấu hình mapping hoặc env
APP_SHEETS = {
    "Quicksave": "1lvUnC7um2wcCBZzzaXDK0MdjDa9OvDcEcyVUOprPtOg"
}

def get_sheet_data_for_app(app_name="Quicksave"):
    if app_name not in APP_SHEETS:
        return {}
    
    sheet_id = APP_SHEETS[app_name]
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred_file = os.path.join(base_dir, "credentials.json")
    
    # Ưu tiên lấy từ biến môi trường Vercel trước
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    credentials = None
    
    if creds_env:
        import json
        try:
            creds_info = json.loads(creds_env)
            credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        except Exception as e:
            pass
            
    if not credentials:
        if not os.path.exists(cred_file):
            return {}
        credentials = Credentials.from_service_account_file(cred_file, scopes=SCOPES)
        
    try:
        gc = gspread.authorize(credentials)
        workspace = gc.open_by_key(sheet_id).sheet1
        
        # Dùng format default để có các key Date dạng "4/8"
        records = workspace.get_all_records()
        
        if not records:
            return {}

            
        app_col = list(records[0].keys())[0] # "26,0" hoặc tên column định kỳ
        metric_col = list(records[0].keys())[2] # ""
        
        # Lấy dòng "Total" của file Quicksave
        total_rows = []
        for r in records:
            val = r.get(app_col)
            if val and str(val).lower() == 'total':
                total_rows.append(r)
                
        metrics_map = {}
        for row in total_rows:
            metric_name = str(row.get(metric_col, '')).strip()
            
            code_id = None
            if "Ads ($)" in metric_name and "#" not in metric_name:
                code_id = 'ads_rev_usd'
            elif "Ads #" in metric_name:
                code_id = 'ads_rev_hash_usd'
            elif "Sub ($)" in metric_name:
                code_id = 'sub_rev_usd'
            elif "thu tổng" in metric_name:
                code_id = 'total_rev_vnd'
            elif "Chi phí" in metric_name:
                code_id = 'cost_vnd'
                
            if code_id:
                for key, val in row.items():
                    key_str = str(key)
                    if "/" in key_str:
                        # Convert "4/8" to "2026-04-08" (Dùng năm hiện tại)
                        try:
                            m, d = map(int, key_str.split('/'))
                            year = datetime.datetime.now().year
                            # Handle end of year rollover if necessary (Ví dụ lấy dữ liệu t12 năm ngoái vào t1)
                            if datetime.datetime.now().month == 1 and m == 12:
                                year -= 1

                            date_str = f"{year}-{m:02d}-{d:02d}"
                            
                            if date_str not in metrics_map:
                                metrics_map[date_str] = {}
                            
                            if val == '' or val is None:
                                val = 0
                            try:
                                metrics_map[date_str][code_id] = float(val)
                            except:
                                metrics_map[date_str][code_id] = 0
                        except:
                            pass
        return metrics_map
        
    except Exception as e:
        print(f"Error reading google sheets for {app_name}: {e}")
        return {}
