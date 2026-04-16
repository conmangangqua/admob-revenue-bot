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
    "Quicksave": "1lvUnC7um2wcCBZzzaXDK0MdjDa9OvDcEcyVUOprPtOg",
    "LunaAI": "1GGbYzBXGaUi0g7fiL1d1AoJyTiLBD3t6W40pYqTzWIU"
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

            
        # Xác định các cột quan trọng
        headers = list(records[0].keys())
        metric_col = headers[2] if len(headers) > 2 else "" # Cột 3 thường là tên Metric
        
        # Tìm các hàng Total (có thể có nhiều hàng cho Doanh thu, Chi phí, Lãi...)
        total_rows = []
        for r in records:
            # Nếu bất kỳ cột nào có chữ chứa từ "tổng" hoặc "total" thì lấy hàng đó
            is_total_row = False
            for val in r.values():
                v_s = str(val).lower().strip()
                if v_s == 'total' or v_s == 'tổng' or v_s == 'tổng cộng' or v_s == 'tổng cộng (vnd)':
                    is_total_row = True
                    break
            if is_total_row:
                total_rows.append(r)
                
        metrics_map = {}
        for row in total_rows:
            code_id = None
            
            # Tìm tên metric: ưu tiên cột metric_col, nếu ko có thì quét hết
            metric_name = str(row.get(metric_col, "")).lower().strip()
            if not any(x in metric_name for x in ["ads", "sub", "doanh thu", "chi phí", "lãi", "lợi nhuận"]):
                for v in row.values():
                    v_str = str(v).lower().strip()
                    if any(x in v_str for x in ["ads", "sub", "doanh thu", "chi phí", "lãi", "lợi nhuận"]):
                        metric_name = v_str
                        break
            
            if "ads ($)" in metric_name and "#" not in metric_name:
                code_id = 'ads_rev_usd'
            elif "ads #" in metric_name:
                code_id = 'ads_rev_hash_usd'
            elif "sub ($)" in metric_name:
                code_id = 'sub_rev_usd'
            elif "doanh thu tổng" in metric_name:
                code_id = 'total_rev_vnd'
            elif "chi phí" in metric_name:
                code_id = 'cost_vnd'
            elif "lãi marketing" in metric_name or "lợi nhuận" in metric_name:
                code_id = 'marketing_profit_vnd'
            elif "lãi/doanh thu" in metric_name or "roi" in metric_name:
                code_id = 'profit_pct_sheet'
                
            if code_id:
                for key, val in row.items():
                    key_str = str(key).strip()
                    # Nhận diện Header ngày tháng (ví dụ: 12/04, 12/4, 4/12...)
                    if "/" in key_str or "-" in key_str:
                        date_parts = key_str.replace('-', '/').split('/')
                        if len(date_parts) == 2:
                            try:
                                # Thử parse ngày tháng linh hoạt
                                p1, p2 = map(int, date_parts)
                                year = datetime.datetime.now().year
                                
                                # Phán đoán đâu là tháng, đâu là ngày (thường là m/d hoặc d/m)
                                if p1 > 12: # p1 là ngày, p2 là tháng
                                    m, d = p2, p1
                                else: # p1 là tháng, p2 là ngày (mặc định)
                                    m, d = p1, p2
                                    
                                date_str = f"{year}-{m:02d}-{d:02d}"
                                if date_str not in metrics_map:
                                    metrics_map[date_str] = {}
                                
                                # Vệ sinh con số: loại bỏ dấu phẩy/chấm để parse chuẩn
                                val_clean = str(val).replace(',', '').strip()
                                metrics_map[date_str][code_id] = val_clean
                            except:
                                continue
        
        def safe_float(v):
            try:
                if not v: return 0.0
                return float(str(v).replace(',', '').strip())
            except:
                return 0.0

        # Sau khi bốc hết, tính toán bổ sung nếu thiếu Chi phí
        for d_str, m_data in metrics_map.items():
            rev = safe_float(m_data.get('total_rev_vnd', 0))
            profit = safe_float(m_data.get('marketing_profit_vnd', 0))
            cost = safe_float(m_data.get('cost_vnd', 0))
            
            # Nếu có doanh thu và lãi nhưng chi phí lại bằng 0 -> Tự tính chi phí
            if rev > 0 and cost == 0 and profit != 0:
                m_data['cost_vnd'] = str(round(rev - profit, 3))
                
        return metrics_map
        
    except Exception as e:
        print(f"Error reading google sheets for {app_name}: {e}")
        return {}


def get_lunaai_sheet_data():
    """
    Parser riêng cho sheet LunaAI Chat vì format khác Quicksave.
    Cấu trúc: hàng = metric (Revenue, Cost, Profit), cột = ngày d/m
    Đơn vị: USD (không phải triệu VND)
    Trả về dict {date_str: {revenue_usd, cost_usd, profit_usd}}
    """
    sheet_id = "1GGbYzBXGaUi0g7fiL1d1AoJyTiLBD3t6W40pYqTzWIU"
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred_file = os.path.join(base_dir, "credentials.json")

    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    credentials = None

    if creds_env:
        import json
        try:
            creds_info = json.loads(creds_env)
            credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        except Exception:
            pass

    if not credentials:
        if not os.path.exists(cred_file):
            return {}
        credentials = Credentials.from_service_account_file(cred_file, scopes=SCOPES)

    try:
        gc = gspread.authorize(credentials)
        ws = gc.open_by_key(sheet_id).sheet1
        all_vals = ws.get_all_values()

        if not all_vals:
            return {}

        # Row 0: header — cột 0 là app code, cột 1 là metric name, cột 2 là tổng,
        #         cột 3..n là tháng/ngày
        header_row = all_vals[0]  # ['88,14', '', '2026,00', 'Tháng 1', ..., '31/3', '1/4', ...]

        # Map index cột → date_str cho các cột có format d/m
        col_date_map = {}
        year = datetime.datetime.now().year
        for ci, cell in enumerate(header_row):
            cell = str(cell).strip()
            if '/' in cell:
                parts = cell.split('/')
                if len(parts) == 2:
                    try:
                        p1, p2 = int(parts[0]), int(parts[1])
                        # Format là d/m
                        if p1 > 12:      # p1 là ngày, p2 là tháng
                            d, m = p1, p2
                        else:            # p1 là ngày <= 12, p2 là tháng
                            d, m = p1, p2
                        col_date_map[ci] = f"{year}-{m:02d}-{d:02d}"
                    except Exception:
                        continue

        def safe_usd(val):
            try:
                return float(str(val).replace(',', '.').strip()) if val else 0.0
            except Exception:
                return 0.0

        METRIC_MAP = {
            'revenue': None,
            'total cost (trước thuế)': None,
            'profit (trước thuế)': None,
        }

        # Gom data theo ngày
        data_by_date = {}

        for row in all_vals[1:]:
            # Xác định tên metric ở cột 1
            metric_raw = str(row[1]).strip().lower() if len(row) > 1 else ''

            if 'revenue' in metric_raw and 'trước thuế' in metric_raw:
                key = 'revenue_usd'
            elif 'total cost' in metric_raw and 'trước thuế' in metric_raw:
                key = 'cost_usd'
            elif 'profit' in metric_raw and 'trước thuế' in metric_raw:
                key = 'profit_usd'
            else:
                continue

            for ci, date_str in col_date_map.items():
                if ci < len(row):
                    val = safe_usd(row[ci])
                    if date_str not in data_by_date:
                        data_by_date[date_str] = {}
                    data_by_date[date_str][key] = val

        return data_by_date

    except Exception as e:
        print(f"Error reading LunaAI sheet: {e}")
        return {}

