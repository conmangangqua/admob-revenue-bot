import os
import gspread
import json
from google.oauth2.service_account import Credentials
import datetime

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly', 'https://www.googleapis.com/auth/drive.readonly']
APP_SHEETS = {"Quicksave": "1lvUnC7um2wcCBZzzaXDK0MdjDa9OvDcEcyVUOprPtOg"}

def debug_sheet(app_name="Quicksave"):
    sheet_id = APP_SHEETS[app_name]
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cred_file = os.path.join(base_dir, "credentials.json")
    creds_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    credentials = None
    if creds_env:
        try:
            creds_info = json.loads(creds_env)
            credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        except: pass
    if not credentials:
        credentials = Credentials.from_service_account_file(cred_file, scopes=SCOPES)
    
    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(sheet_id)
    ws = sh.sheet1
    rows = ws.get_all_values()
    
    print("--- HEADERS (First 2 rows) ---")
    for i in range(min(len(rows), 2)):
        print(f"Row {i}: {rows[i]}")
        
    print("\n--- SAMPLE ROWS (Searching for 'Total' or metrics) ---")
    for i, row in enumerate(rows):
        if any('total' in str(v).lower() or 'chi phí' in str(v).lower() or 'thu tổng' in str(v).lower() for v in row):
            print(f"Row {i}: {row}")
            if i > 50: break # Don't dump too much

if __name__ == "__main__":
    debug_sheet()
