# 📊 GA Revenue Discord Bot

Bot tự động thống kê doanh thu ads hàng ngày (GA4 Data API) và gửi báo cáo lên Discord.

## Tính Năng
- ✅ Tự động chạy lúc **7:45 AM giờ Việt Nam** mỗi ngày (GitHub Actions)
- ✅ **v6.0 (2026-07-27)**: đọc thẳng GA4 bằng service account `hub-admin-sa` — tự
  discover MỌI property qua `accountSummaries`, app mới tự xuất hiện, không cần sửa code
- ✅ Hiển thị **revenue, impressions, eCPM** từng app, gom theo partner
- ✅ So sánh **% thay đổi** so với hôm qua (xanh/đỏ)
- ✅ Nguồn bổ sung: Looker Studio sync (launchd local) + Azura CSV

---

## 🚀 Hướng Dẫn Setup (Làm 1 Lần)

### Bước 1: Quyền GA cho service account

Nhờ chủ từng GA account vào **analytics.google.com → Admin → Account Access Management**
add `hub-admin-sa@apps-status-reader.iam.gserviceaccount.com` role **Viewer** (cấp account).

### Bước 2: Tạo key cho SA (nếu chưa có)

```bash
gcloud iam service-accounts keys create /tmp/hub-admin-sa.json \
  --iam-account=hub-admin-sa@apps-status-reader.iam.gserviceaccount.com
```

### Bước 3: Tạo Discord Webhook

1. Vào Discord Channel → **Edit Channel → Integrations → Webhooks**
2. **New Webhook** → Copy Webhook URL

### Bước 4: Thêm GitHub Secrets

Vào GitHub Repo → **Settings → Secrets and variables → Actions → New secret**

| Secret Name | Giá trị |
|---|---|
| `HUB_ADMIN_SA_KEY` | Toàn bộ nội dung JSON key từ Bước 2 |
| `DISCORD_WEBHOOK_URL` | Webhook URL từ Bước 3 |

(Chạy local trên Mac không cần key — tự fallback `gcloud` impersonation.)

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
│   ├── ga_client.py                   # GA4 Data API qua SA (v6.0)
│   ├── discord_client.py              # Discord Webhook sender
│   └── sync_looker_daily.py          # Looker sync (launchd local)
├── data/
│   ├── revenue_history.json           # Lịch sử doanh thu (dashboard đọc)
│   └── ga_names.json                  # Map GA property → tên app đẹp
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
