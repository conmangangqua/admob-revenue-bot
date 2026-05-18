#!/usr/bin/env bash
# Render plist từ template với path động + bootstrap vào launchd (macOS modern API).
#
# Usage:
#   ./launchd/install.sh              # mặc định 3 lần/ngày: 08:30, 13:30, 20:30
#   ./launchd/install.sh 14 30        # 1 lần/ngày lúc 14:30
#   ./launchd/install.sh "8 0,13 0,20 0"   # nhiều mốc tùy chỉnh
#   ./launchd/install.sh --uninstall  # gỡ
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LABEL="com.conmangangqua.looker-sync"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"

if [[ "${1:-}" == "--uninstall" ]]; then
    if [[ -f "$TARGET_PLIST" ]]; then
        launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
        rm "$TARGET_PLIST"
        echo "[✓] Đã gỡ $LABEL."
    else
        echo "[i] Không có gì để gỡ."
    fi
    exit 0
fi

# Xác định danh sách mốc giờ chạy.
# - 0 args        → default 3 mốc (sáng/chiều/tối) chống máy ngủ + backfill data trễ
# - 2 args (H M)  → 1 mốc duy nhất
# - 1 arg "H M,H M,..." → nhiều mốc tùy chỉnh
if [[ -z "${1:-}" ]]; then
    TIMES="8 30,13 30,20 30"
elif [[ -n "${2:-}" ]]; then
    TIMES="$1 $2"
else
    TIMES="$1"
fi

# Build XML array các <dict><Hour><Minute>
CAL_XML=""
IFS=',' read -ra _slots <<< "$TIMES"
for slot in "${_slots[@]}"; do
    h="$(echo "$slot" | awk '{print $1}')"
    m="$(echo "$slot" | awk '{print $2}')"
    m="${m:-0}"
    CAL_XML+="        <dict><key>Hour</key><integer>${h}</integer><key>Minute</key><integer>${m}</integer></dict>"$'\n'
done
CAL_XML="${CAL_XML%$'\n'}"

# Ưu tiên venv nếu tồn tại (PEP 668 → Homebrew Python block pip system-wide)
if [[ -x "$REPO_DIR/.venv/bin/python3" ]]; then
    PYTHON_BIN="$REPO_DIR/.venv/bin/python3"
    echo "[i] Detected venv → dùng $PYTHON_BIN"
else
    PYTHON_BIN="$(command -v python3 || true)"
    if [[ -z "$PYTHON_BIN" ]]; then
        echo "[X] Không tìm thấy python3 trong PATH." >&2
        exit 1
    fi
    echo "[!] Không thấy .venv → dùng system $PYTHON_BIN (cẩn thận PEP 668)."
fi
PYTHON_DIR="$(dirname "$PYTHON_BIN")"
FULL_PATH="$PYTHON_DIR:/usr/local/bin:/usr/bin:/bin"

# Log directory: external volume (/Volumes/...) bị launchd chặn ghi stdout/stderr trên
# macOS Sequoia (TCC) → EX_CONFIG 78. Fallback sang ~/Library/Logs/<label>/ luôn an toàn.
if [[ "$REPO_DIR" == /Volumes/* ]]; then
    LOG_DIR="$HOME/Library/Logs/$LABEL"
    echo "[i] Workdir nằm trên external volume → log → $LOG_DIR"
else
    LOG_DIR="$REPO_DIR/launchd"
fi
mkdir -p "$LOG_DIR"

TEMPLATE="$SCRIPT_DIR/$LABEL.plist.template"
RENDERED="$SCRIPT_DIR/$LABEL.plist"

sed \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    -e "s|__WORKDIR__|$REPO_DIR|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    -e "s|__PATH__|$FULL_PATH|g" \
    "$TEMPLATE" > "$RENDERED"

# Thay __CAL_INTERVALS__ (multiline) bằng Python cho an toàn
CAL_XML="$CAL_XML" python3 - "$RENDERED" <<'PYEOF'
import os, sys
p = sys.argv[1]
with open(p) as f:
    txt = f.read()
txt = txt.replace("__CAL_INTERVALS__", os.environ["CAL_XML"])
with open(p, "w") as f:
    f.write(txt)
PYEOF

mkdir -p "$HOME/Library/LaunchAgents"

# Modern launchctl: bootstrap thay vì load. Plist BẮT BUỘC là file thật, KHÔNG symlink
# (bootstrap reject symlink với "Input/output error" trên macOS Sequoia).
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
rm -f "$TARGET_PLIST"
cp "$RENDERED" "$TARGET_PLIST"
chmod 644 "$TARGET_PLIST"
launchctl bootstrap "$DOMAIN" "$TARGET_PLIST"

echo "[✓] Đã cài $LABEL"
echo "    Python:  $PYTHON_BIN"
echo "    Workdir: $REPO_DIR"
echo "    Times:   $TIMES (hằng ngày) + chạy ngay khi load/login"
echo "    Logs:    $LOG_DIR/sync.{out,err}.log"
echo ""
echo "Test ngay: launchctl start $LABEL"
