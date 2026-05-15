"""
Cookie Refresher cho Looker Studio (Google Data Studio).

Cách dùng:
- `python3 scripts/cookie_refresher.py --login`
    → mở Chrome thật, login Google tay, capture cookies → lưu vào `looker_cookies.json`.
- `python3 scripts/cookie_refresher.py`
    → KHÔNG mở browser. Đọc cookies từ `looker_cookies.json`.

LƯU Ý quan trọng: KHÔNG dùng headless Chrome re-fetch cookies. Google block headless
→ session poison → API trả 401. Tin tưởng cookies từ --login session dùng được ~2 tuần.
Khi API trả 401, chạy lại --login.
"""

import argparse
import json
import sys
from pathlib import Path

REPORT_URL = (
    "https://datastudio.google.com/u/0/reporting/"
    "2a3eaf2b-5c24-47e1-b447-eb33cd2c12bc/page/0TxaF"
)

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "chrome_profile"
COOKIE_FILE = BASE_DIR / "looker_cookies.json"

ANTI_DETECT_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
]


def do_login() -> dict:
    """Mở Chrome headed, đợi user login → capture cookies."""
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            args=ANTI_DETECT_ARGS,
            viewport={"width": 1280, "height": 800},
            ignore_default_args=["--enable-automation"],
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=60_000)

        print(
            "[!] Đăng nhập Google. Sau khi report Looker hiển thị bảng dữ liệu, "
            "quay lại terminal và nhấn Enter.",
            file=sys.stderr,
        )
        input()

        cookies = context.cookies()
        context.close()

    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    xsrf = next((c["value"] for c in cookies if c["name"] == "RAP_XSRF_TOKEN"), "")

    if not xsrf:
        raise RuntimeError(
            "Không tìm thấy RAP_XSRF_TOKEN. Có thể chưa vào được trang report. "
            "Đảm bảo report đã load xong trước khi nhấn Enter."
        )

    result = {"cookie": cookie_header, "xsrf": xsrf}
    COOKIE_FILE.write_text(json.dumps(result, indent=2))
    print(f"[✓] Đã lưu cookies vào {COOKIE_FILE}", file=sys.stderr)
    return result


def load_cookies() -> dict:
    """Đọc cookies đã lưu. Không launch browser."""
    if not COOKIE_FILE.exists():
        raise RuntimeError(
            f"Chưa có {COOKIE_FILE.name}. Chạy `cookie_refresher.py --login` trước."
        )
    return json.loads(COOKIE_FILE.read_text())


def refresh(login_mode: bool = False) -> dict:
    if login_mode:
        return do_login()
    return load_cookies()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--export-env", action="store_true")
    args = parser.parse_args()

    result = refresh(login_mode=args.login)

    if args.export_env:
        cookie_esc = result["cookie"].replace("'", "'\\''")
        xsrf_esc = result["xsrf"].replace("'", "'\\''")
        print(f"export LOOKER_COOKIE='{cookie_esc}'")
        print(f"export LOOKER_XSRF='{xsrf_esc}'")
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
