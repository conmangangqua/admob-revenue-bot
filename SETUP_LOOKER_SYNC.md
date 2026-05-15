# Setup Auto-Sync Looker Studio — Hằng Ngày

Hệ thống tự fetch dữ liệu Looker Studio mỗi ngày → merge vào `data/revenue_history.json` → commit & push. Chạy qua `launchd` (cron của macOS) bằng headless Chrome thật + Playwright intercept response.

## Tổng quan kiến trúc

```
launchd cron → sync_looker_daily.py
                  └→ looker_browser_fetcher.py
                       └→ headless Chrome (chrome_profile/)
                            └→ navigate Looker report
                                 └→ intercept response batchedDataV2
                                      → parse rows → merge JSON → git push
```

**Quan trọng**:
- KHÔNG replay cookies qua `requests` (Google chặn → 401).
- Dùng **Chrome thật** của hệ thống (`channel="chrome"`) với persistent profile.
- Profile login (chrome_profile/) lưu local từng máy, không lên git.

---

## QUICKSTART — Cài lần đầu trên máy mới

Copy/paste nguyên khối, sửa giờ stagger nếu muốn (mặc định 14:00):

```bash
# 1. Clone repo
git clone https://github.com/conmangangqua/admob-revenue-bot.git
cd admob-revenue-bot

# 2. Cài Python deps (BẮT BUỘC venv vì macOS chặn pip system-wide - PEP 668)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium

# 3. Login Google Looker (sẽ mở Chrome thật → login tay → Enter)
.venv/bin/python3 scripts/cookie_refresher.py --login
# ↑ Chrome mở → login Google → ĐỢI report Looker hiện bảng số liệu → quay terminal Enter

# 4. Test pipeline trước khi cài cron
.venv/bin/python3 scripts/sync_looker_daily.py --no-commit
# ↑ Phải thấy "→ 250 rows nhận về" và merge OK. Nếu < 50 rows → session lỗi, chạy lại bước 3.

# 5. Cài cron launchd (mặc định 08:00, sửa giờ tùy ý)
./launchd/install.sh 14 0    # → chạy 14:00 hằng ngày
# Hoặc: ./launchd/install.sh        # → mặc định 08:00

# 6. Test cron chạy ngay
launchctl start com.conmangangqua.looker-sync
sleep 90
tail -30 launchd/sync.out.log launchd/sync.err.log
launchctl list | grep looker-sync   # cột 2 = 0 là OK
```

---

## Multi-Machine: chạy trên >1 máy

Hoàn toàn được. Có 2 lưu ý:

1. **`chrome_profile/` per-machine** (gitignored): mỗi máy phải tự `--login` lần đầu.
2. **Race khi git push**: `sync_looker_daily.py` đã có **auto `git pull --rebase --autostash` retry 3 lần** chống race. Yên tâm.

**Khuyến nghị stagger giờ** để có 2-3 lần refresh/ngày:
- Máy chính: `./launchd/install.sh 8 0` (08:00)
- Máy phụ:   `./launchd/install.sh 14 0` (14:00)
- Máy laptop: không cài cron, chạy tay khi cần: `.venv/bin/python3 scripts/sync_looker_daily.py`

---

## Vận hành hằng ngày

### Xem log
```bash
tail -100 launchd/sync.out.log    # success
tail -100 launchd/sync.err.log    # error / progress
```

### Trigger thủ công
```bash
launchctl start com.conmangangqua.looker-sync
```

### Xem trạng thái job
```bash
launchctl list | grep looker-sync
# Format: <PID>  <ExitCode>  com.conmangangqua.looker-sync
# PID = "-" → idle. ExitCode = 0 → lần chạy gần nhất OK.
```

### Gỡ cron
```bash
./launchd/install.sh --uninstall
```

### Đổi giờ
```bash
./launchd/install.sh --uninstall
./launchd/install.sh <hour> <minute>
```

---

## Troubleshooting

### Triệu chứng: log báo `HTTP 401` hoặc `Không tìm thấy bảng revenue`
→ Google session hết hạn (thường 2-4 tuần). Fix:
```bash
.venv/bin/python3 scripts/cookie_refresher.py --login
```

### Triệu chứng: chỉ fetch được 6 rows thay vì 250
→ Headless Chrome chưa kịp load full table. Đã fix bằng cách đợi đến khi response có ≥50 rows. Nếu vẫn lặp lại → tăng `timeout_ms` trong `looker_browser_fetcher.py:fetch()`.

### Triệu chứng: `pip install` báo `externally-managed-environment`
→ Đang dùng Homebrew Python system-wide. BẮT BUỘC dùng venv (xem QUICKSTART bước 2).

### Triệu chứng: `git commit fail` với stderr trống
→ Đã fix: pre-check bằng `git diff --cached --quiet`. Nếu vẫn gặp → có thể conflict, xem `git status`.

---

## Files & cấu trúc

| File | Vai trò | Tracked |
|------|---------|---------|
| `scripts/cookie_refresher.py` | Mở Chrome headed cho user login | ✅ |
| `scripts/looker_browser_fetcher.py` | Headless Chrome intercept API response | ✅ |
| `scripts/sync_looker_daily.py` | Orchestrator + merge + git push | ✅ |
| `launchd/com.conmangangqua.looker-sync.plist.template` | Template cron | ✅ |
| `launchd/install.sh` | Renderer + installer động | ✅ |
| `launchd/com.conmangangqua.looker-sync.plist` | Rendered output (per-machine) | ❌ |
| `chrome_profile/` | Chrome profile + cookies Google session | ❌ |
| `looker_cookies.json` | Legacy, có thể xoá | ❌ |
| `.venv/` | Python venv | ❌ |
| `launchd/sync.{out,err}.log` | Cron logs | ❌ |
