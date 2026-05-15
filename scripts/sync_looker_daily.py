"""
Sync hằng ngày: refresh cookie Looker → fetch data → merge vào revenue_history.json → git commit/push.

Chạy:
    python3 scripts/sync_looker_daily.py
        [--no-commit]   # bỏ qua git commit/push (debug local)
        [--dry-run]     # chỉ fetch, in ra, không ghi file
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.looker_browser_fetcher import fetch as fetch_via_browser  # noqa: E402

HISTORY_FILE = BASE_DIR / "data" / "revenue_history.json"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(data: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def merge_rows(history: dict, rows: list) -> int:
    """Merge các row từ Looker vào history. Trả về số app records đã update."""
    touched = 0
    for row in rows:
        date_key = (row.get("date") or "").strip()
        if not date_key:
            continue

        app_code = (row.get("app_code") or "").strip()
        app_name = (row.get("app_name") or "").strip()
        if not app_code:
            continue

        display_name = f"{app_code} - {app_name}" if app_name else app_code
        ads_rev = float(row.get("admob_revenue") or 0)
        google_sp = float(row.get("google_spend") or 0)
        mint_sp = float(row.get("mintegral_spend") or 0)
        tiktok_sp = float(row.get("tiktok_spend") or 0)
        fb_sp = float(row.get("facebook_spend") or 0)

        day_entry = history.setdefault(date_key, {"total": 0, "apps": []})
        apps = day_entry.setdefault("apps", [])

        existing = next(
            (
                a
                for a in apps
                if a.get("name") == display_name
                or (a.get("name") or "").startswith(f"{app_code} -")
            ),
            None,
        )

        new_data = {
            "name": display_name,
            "rev": round(ads_rev, 2),
            "imp": (existing or {}).get("imp", 0),
            "ecpm": (existing or {}).get("ecpm", 0),
            "google_spend": round(google_sp, 2),
            "mintegral_spend": round(mint_sp, 2),
            "tiktok_spend": round(tiktok_sp, 2),
            "facebook_spend": round(fb_sp, 2),
        }
        if existing and "sheet_data" in existing:
            new_data["sheet_data"] = existing["sheet_data"]

        if existing:
            existing.update(new_data)
        else:
            apps.append(new_data)
        touched += 1

    for date_key, day in history.items():
        total = sum(a.get("rev", 0) for a in day.get("apps", []))
        day["total"] = round(total, 2)

    return touched


def _run_git(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)


def git_commit_push(message: str, max_retry: int = 3) -> None:
    """Commit + push với rebase-guard chống race khi nhiều máy cùng sync."""
    add = _run_git(["git", "add", "data/revenue_history.json"])
    if add.returncode != 0:
        print(f"[!] git add fail: {add.stderr.strip()}", file=sys.stderr)
        sys.exit(2)

    # Pre-check: có thay đổi staged không?
    diff_check = _run_git(["git", "diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        print("[i] Không có thay đổi → bỏ qua commit/push.")
        return

    commit = _run_git(["git", "commit", "-m", message])
    if commit.returncode != 0:
        print(
            f"[!] git commit fail (out={commit.stdout.strip()!r} "
            f"err={commit.stderr.strip()!r})",
            file=sys.stderr,
        )
        sys.exit(2)

    for attempt in range(1, max_retry + 1):
        push = _run_git(["git", "push"])
        if push.returncode == 0:
            print("[✓] Đã commit & push thành công.")
            return

        stderr = (push.stderr or "").lower()
        is_race = any(
            kw in stderr
            for kw in ("non-fast-forward", "fetch first", "rejected", "tip of your current branch is behind")
        )
        if not is_race or attempt == max_retry:
            print(f"[!] git push fail: {push.stderr.strip()}", file=sys.stderr)
            sys.exit(2)

        print(f"[!] Push bị reject (race với máy khác) → pull --rebase (lần {attempt}/{max_retry})…")
        rebase = _run_git(["git", "pull", "--rebase", "--autostash"])
        if rebase.returncode != 0:
            print(f"[!] Rebase fail: {rebase.stderr.strip()}", file=sys.stderr)
            _run_git(["git", "rebase", "--abort"])
            sys.exit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[1/2] Fetch data từ Looker (browser intercept)…")
    try:
        rows = fetch_via_browser(login_mode=False, headless=True)
    except RuntimeError as e:
        print(f"[X] {e}", file=sys.stderr)
        sys.exit(1)
    print(f"    → {len(rows)} rows nhận về.")

    if args.dry_run:
        print(json.dumps(rows[:3], indent=2, ensure_ascii=False))
        return

    print(f"[2/2] Merge vào {HISTORY_FILE.name}…")
    history = load_history()
    touched = merge_rows(history, rows)
    save_history(history)
    print(f"    → {touched} app-record đã update.")

    if args.no_commit:
        return

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    git_commit_push(f"chore(data): auto-sync Looker {stamp}")


if __name__ == "__main__":
    main()
