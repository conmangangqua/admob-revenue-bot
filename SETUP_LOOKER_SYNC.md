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
# ↑ Phải thấy "→ 4xx rows nhận về" (replay rowsCount=5000) và merge OK.
#   Nếu < 50 rows → session lỗi, chạy lại bước 3.

# 5. Cài cron launchd (mặc định 3 mốc/ngày: 08:30, 13:30, 20:30 + chạy khi load)
./launchd/install.sh              # → 3 mốc/ngày (KHUYẾN NGHỊ - chống máy ngủ)
# Hoặc: ./launchd/install.sh 14 0          # 1 mốc 14:00
# Hoặc: ./launchd/install.sh "8 0,14 0,21 0"  # mốc tùy chỉnh

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
# Repo nằm trên ổ internal:
tail -100 launchd/sync.out.log    # success
tail -100 launchd/sync.err.log    # error / progress

# Repo nằm trên external volume (/Volumes/...) — install.sh tự redirect:
tail -100 ~/Library/Logs/com.conmangangqua.looker-sync/sync.out.log
tail -100 ~/Library/Logs/com.conmangangqua.looker-sync/sync.err.log
```
> launchd trên macOS Sequoia (15.x) chặn ghi stdout/stderr trên external volume → EX_CONFIG 78. `install.sh` tự phát hiện và fallback sang `~/Library/Logs/<label>/`. In ra path thật ở cuối lệnh `install.sh`.

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

### Triệu chứng: chỉ fetch được 6 rows / thiếu app (B087, B081…)
→ Đã fix: replay request với `rowsCount=5000` (mặc định report chỉ 250 → cắt mất app cuối). Giờ lấy đủ ~4xx rows.

### Triệu chứng: data ngày hôm qua chưa có app Azura
→ **Bình thường**. Azura/Looker finalize data trễ 1-2 ngày. Cron chạy nhiều mốc/ngày + merge tự backfill ngày cũ khi data về. Sáng xem "hôm qua" có thể chưa đủ — đợi 1-2 hôm sẽ tự đầy.

### Triệu chứng: launchd không chạy (log mtime đứng yên nhiều ngày)
→ Mac ngủ vào giờ cron → user-agent job không fire. Đã giảm thiểu bằng 3 mốc/ngày + `RunAtLoad` (chạy ngay khi login/wake). Nếu cần chắc 100%: giữ Mac không sleep, hoặc `sudo pmset repeat wakeorpoweron MTWRFSU 08:25:00`.

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
| `launchd/sync.{out,err}.log` | Cron logs (khi repo trên ổ internal) | ❌ |
| `~/Library/Logs/com.conmangangqua.looker-sync/sync.{out,err}.log` | Cron logs (khi repo trên external volume) | ❌ |
