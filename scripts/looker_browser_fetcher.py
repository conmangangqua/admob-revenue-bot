"""
Fetch data Looker bằng cách để Chrome thật navigate vào report → intercept
response API `batchedDataV2`. Tránh việc replay cookies qua requests (Google 401).

Usage:
    python3 scripts/looker_browser_fetcher.py --login     # login lần đầu, headed
    python3 scripts/looker_browser_fetcher.py             # headed (default)
    python3 scripts/looker_browser_fetcher.py --headless  # cron mode

Output: JSON rows list ra stdout.
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPORT_URL = (
    "https://datastudio.google.com/u/0/reporting/"
    "2a3eaf2b-5c24-47e1-b447-eb33cd2c12bc/page/0TxaF"
)
API_PATTERN = "batchedDataV2"

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "chrome_profile"

ANTI_DETECT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate",
]


def parse_response_text(text: str) -> dict:
    if text.startswith(")]}'"):
        text = text[4:].strip()
    return json.loads(text)


def parse_rows(raw: dict) -> list:
    """Parse 1 raw response batchedDataV2 thành list rows."""
    try:
        ds = raw["dataResponse"][0]["dataSubset"][0]["dataset"]["tableDataset"]
        columns = ds.get("column", [])
    except (KeyError, IndexError, TypeError):
        return []

    def vals(col):
        for key in ("stringColumn", "doubleColumn", "dateColumn", "int64Column"):
            if key in col:
                return col[key].get("values", [])
        return []

    cols = [vals(c) for c in columns]
    if not cols or not cols[0]:
        return []

    # Mapping 13 cột (xác minh EXACT bằng đối chiếu Azura.csv ngày đã finalized):
    # 0 app_code | 1 app_name | 2 date | 3 calc-KHÔNG-DÙNG (không phải %PL2)
    # 4 Rev(VND) | 5 Cost MKT(VND) | 6 MKT Profit(VND) | 7 Ads Rev(USD)
    # 8 Google | 9 Mintegral | 10 Tiktok | 11 Facebook | 12 Exchange Rate
    # %PL2 thật = profit_vnd/rev_vnd*100 (tính ở merge), KHÔNG lấy col3.
    n = len(cols[0])
    rows = []
    for i in range(n):
        def cell(idx, default=""):
            return cols[idx][i] if idx < len(cols) and i < len(cols[idx]) else default
        rows.append({
            "app_code": cell(0),
            "app_name": cell(1),
            "date": cell(2),
            "rev_vnd": cell(4, 0.0),
            "cost_vnd": cell(5, 0.0),
            "profit_vnd": cell(6, 0.0),
            "admob_revenue": cell(7, 0.0),
            "google_spend": cell(8, 0.0),
            "mintegral_spend": cell(9, 0.0),
            "tiktok_spend": cell(10, 0.0),
            "facebook_spend": cell(11, 0.0),
        })
    return rows


def looks_like_revenue_table(rows: list) -> bool:
    """Filter: bảng đúng là bảng có app_code dạng 'B...' (B081, B087, ...)."""
    if not rows:
        return False
    for r in rows[:5]:
        code = str(r.get("app_code") or "").strip()
        if code.startswith("B") and len(code) <= 6:
            return True
    return False


def fetch(login_mode: bool = False, headless: bool = False, timeout_ms: int = 60_000) -> list:
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    captured = []  # list[dict] — raw responses

    def on_response(response):
        try:
            if API_PATTERN not in response.url or response.request.method != "POST":
                return
            if response.status != 200:
                print(f"[!] {API_PATTERN} HTTP {response.status}", file=sys.stderr)
                return
            text = response.text()
            data = parse_response_text(text)
            captured.append(data)
        except Exception as e:
            print(f"[!] on_response error: {e}", file=sys.stderr)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=headless and not login_mode,
            args=ANTI_DETECT_ARGS,
            viewport={"width": 1400, "height": 900},
            ignore_default_args=["--enable-automation"],
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", on_response)

        print(f"[i] Mở report…", file=sys.stderr)
        page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=timeout_ms)

        if login_mode:
            print(
                "[!] Login Google nếu chưa. Đợi report hiện bảng số liệu (B081, B087,…), "
                "rồi nhấn Enter.",
                file=sys.stderr,
            )
            input()
        else:
            # Đợi đến khi intercept được response chính (table revenue có nhiều rows).
            # Headless render chậm hơn headed nên không thể chỉ dựa vào networkidle.
            deadline = time.time() + timeout_ms / 1000
            while time.time() < deadline:
                got_full = False
                for resp in captured:
                    rows = parse_rows(resp)
                    if looks_like_revenue_table(rows) and len(rows) >= 50:
                        got_full = True
                        break
                if got_full:
                    page.wait_for_timeout(2_000)  # buffer phòng response sau
                    break
                page.wait_for_timeout(1_000)
            else:
                print(
                    "[!] Hết timeout chưa thấy response đủ rows — sẽ thử parse những gì có.",
                    file=sys.stderr,
                )

        context.close()

    print(f"[i] Intercepted {len(captured)} responses.", file=sys.stderr)

    # Tìm response chứa bảng revenue (app_code 'B...'), ưu tiên cái nhiều rows nhất
    best = []
    for resp in captured:
        rows = parse_rows(resp)
        if looks_like_revenue_table(rows) and len(rows) > len(best):
            best = rows
    if best:
        return best

    raise RuntimeError(
        f"Không tìm thấy bảng revenue trong {len(captured)} response. "
        "Session có thể đã hết hạn → chạy lại với --login."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    rows = fetch(login_mode=args.login, headless=args.headless)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"[i] Total rows: {len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    main()
