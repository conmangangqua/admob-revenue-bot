import csv
import json
import os
from datetime import datetime

def update_json_from_csv():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_file = os.path.join(base_dir, "Azura.csv")
    json_file = os.path.join(base_dir, "data", "revenue_history.json")

    if not os.path.exists(csv_file):
        print(f"File {csv_file} không tồn tại!")
        return

    # Khởi tạo history dictionary
    history_data = {}
    if os.path.exists(json_file):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        except Exception as e:
            print(f"Lỗi đọc JSON: {e}")

    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # CSV có Day dạng MM/DD/YYYY
                    day_str = row['Day'].strip()
                    if not day_str: continue

                    dt = datetime.strptime(day_str, "%m/%d/%Y")
                    date_key = dt.strftime("%Y-%m-%d")

                    # Map metrics
                    app_code = row['App Code'].strip()
                    app_name = row['App Name'].strip()
                    display_name = f"{app_code} - {app_name}"

                    # Ads Rev là doanh thu USD
                    ads_rev_str = row['Ads Rev'].strip()
                    ads_rev = float(ads_rev_str) if ads_rev_str and ads_rev_str != '-' else 0.0

                    # Spends (USD)
                    google_sp = float(row.get('Google', 0).strip() or 0)
                    mint_sp = float(row.get('Mintergral', 0).strip() or 0)
                    tiktok_sp = float(row.get('Tiktok', 0).strip() or 0)
                    fb_sp = float(row.get('Facebook', 0).strip() or 0)
                    
                    # Cột (VND)
                    rev_vnd = float(row.get('Rev (VND)', 0).strip().replace(',', '') or 0)
                    cost_vnd = float(row.get('Cost MKT (VND)', 0).strip().replace(',', '') or 0)
                    profit_vnd = float(row.get('MKT Profit (VND)', 0).strip().replace(',', '') or 0)

                    # %PL2
                    pl2 = row.get('%PL2', '0').strip()

                    # Convert VND ra triệu VND (chia 1,000,000)
                    rev_mil = rev_vnd / 1000000.0
                    cost_mil = cost_vnd / 1000000.0
                    profit_mil = profit_vnd / 1000000.0

                    profit_pct = "0%"
                    if pl2 != '-' and float(pl2) != 0:
                        profit_pct = f"{round(float(pl2))}%"
                    elif rev_vnd != 0:
                        profit_pct = f"{round((profit_vnd / rev_vnd)*100)}%"

                    # Cập nhật vào history_data
                    if date_key not in history_data:
                        history_data[date_key] = {"total": 0, "apps": []}
                    
                    apps_list = history_data[date_key].get("apps", [])
                    
                    # Tìm xem app đã có chưa
                    existing_app = None
                    for a in apps_list:
                        if a.get("name") == display_name or a.get("name").startswith(f"{app_code} -"):
                            existing_app = a
                            break
                    
                    new_app_data = {
                        "name": display_name,
                        "rev": round(ads_rev, 2),
                        "imp": 0,
                        "ecpm": 0,
                        "google_spend": round(google_sp, 2),
                        "mintegral_spend": round(mint_sp, 2),
                        "tiktok_spend": round(tiktok_sp, 2),
                        "facebook_spend": round(fb_sp, 2),
                        "sheet_data": {
                            "total_rev_vnd": str(round(rev_mil, 3)),
                            "cost_vnd": str(round(cost_mil, 3)),
                            "marketing_profit_vnd": str(round(profit_mil, 3)),
                            "profit_pct_sheet": profit_pct
                        }
                    }

                    if existing_app:
                        existing_app.update(new_app_data)
                    else:
                        apps_list.append(new_app_data)
                    
                    history_data[date_key]["apps"] = apps_list
                    
                except Exception as ex:
                    print(f"Lỗi parse dòng {row}: {ex}")

        # Tính lại toàn bộ total để đảm bảo chính xác
        for date_key, day_info in history_data.items():
            total = 0
            if "apps" in day_info:
                for a in day_info["apps"]:
                    total += a.get("rev", 0)
            day_info["total"] = round(total, 2)

        # Ghi lại file JSON
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)
            
        print("✅ Đã cập nhật Azura.csv vào revenue_history.json thành công!")
        
    except Exception as e:
        print(f"Lỗi: {e}")

if __name__ == "__main__":
    update_json_from_csv()
