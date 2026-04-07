# 📊 AdMob Revenue Discord Bot

Bot tự động thống kê doanh thu AdMob hàng ngày và gửi báo cáo lên Discord.

## Tính Năng
- ✅ Tự động chạy lúc **8:00 AM giờ Việt Nam** mỗi ngày
- ✅ Hỗ trợ **nhiều app** trong cùng tài khoản AdMob
- ✅ Hiển thị **revenue, impressions, eCPM** từng app
- ✅ So sánh **% thay đổi** so với hôm qua (xanh/đỏ)
- ✅ Chạy **miễn phí** qua GitHub Actions

---

## 🚀 Hướng Dẫn Setup (Làm 1 Lần)

### Bước 1: Tạo OAuth2 Credentials

1. Vào **[Google Cloud Console](https://console.cloud.google.com)**
2. Tạo project mới hoặc chọn project có sẵn
3. Vào **APIs & Services → Enable APIs**
   - Tìm và enable: **AdMob API**
4. Vào **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Desktop app**
   - Tên: `admob-revenue-bot` (tùy ý)
5. Download JSON → lấy `client_id` và `client_secret`

### Bước 2: Lấy Refresh Token (Chạy 1 lần)

```bash
pip install -r requirements.txt
python scripts/get_refresh_token.py
```

Script sẽ mở trình duyệt → đăng nhập Google → tự động lấy token.  
Sau đó copy 3 giá trị in ra terminal.

### Bước 3: Tạo Discord Webhook

1. Vào Discord Channel → **Edit Channel → Integrations → Webhooks**
2. **New Webhook** → Copy Webhook URL

### Bước 4: Thêm GitHub Secrets

Vào GitHub Repo → **Settings → Secrets and variables → Actions → New secret**

| Secret Name | Giá trị |
|---|---|
| `ADMOB_CLIENT_ID` | Client ID từ Bước 1 |
| `ADMOB_CLIENT_SECRET` | Client Secret từ Bước 1 |
| `ADMOB_REFRESH_TOKEN` | Refresh Token từ Bước 2 |
| `DISCORD_WEBHOOK_URL` | Webhook URL từ Bước 3 |

### Bước 5: Test Thủ Công

Vào **GitHub → Actions → Daily AdMob Revenue Report → Run workflow**

---

## 📁 Cấu Trúc File

```
admob-revenue-bot/
├── .github/
│   └── workflows/
│       └── daily-revenue-report.yml  # Schedule & trigger
├── scripts/
│   ├── main.py                        # Entry point
│   ├── admob_client.py                # AdMob API wrapper
│   ├── discord_client.py              # Discord Webhook sender
│   └── get_refresh_token.py          # Auth 1 lần (chạy local)
├── requirements.txt
└── README.md
```

---

## 📊 Discord Report Preview

```
💹 AdMob Revenue — Thứ 2, 07/04/2026

📊 Tổng Quan
💰 Tổng Revenue: $236.30
👁 Impressions: 12,450
📈 +12.4% so hôm qua ($210.22)

📱 Chi tiết 3 Apps
🥇 B098 - Ai Art
💵 $145.30 ████████  👁 7,200  eCPM $20.18

🥈 B099 - PDF Tool  
💵 $67.20 ████░░░░  👁 3,800  eCPM $17.68

🥉 B100 - Scanner
💵 $23.80 ██░░░░░░  👁 1,450  eCPM $16.41
```
