#!/usr/bin/env bash
# Render plist từ template với path động + load vào launchd.
#
# Usage:
#   ./launchd/install.sh              # mặc định 08:00
#   ./launchd/install.sh 14 30        # giờ 14:30
#   ./launchd/install.sh --uninstall  # gỡ
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
LABEL="com.conmangangqua.looker-sync"
TARGET_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "--uninstall" ]]; then
    if [[ -f "$TARGET_PLIST" ]]; then
        launchctl unload "$TARGET_PLIST" 2>/dev/null || true
        rm "$TARGET_PLIST"
        echo "[✓] Đã gỡ $LABEL."
    else
        echo "[i] Không có gì để gỡ."
    fi
    exit 0
fi

HOUR="${1:-8}"
MINUTE="${2:-0}"

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

TEMPLATE="$SCRIPT_DIR/$LABEL.plist.template"
RENDERED="$SCRIPT_DIR/$LABEL.plist"

sed \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    -e "s|__WORKDIR__|$REPO_DIR|g" \
    -e "s|__HOUR__|$HOUR|g" \
    -e "s|__MINUTE__|$MINUTE|g" \
    -e "s|__PATH__|$FULL_PATH|g" \
    "$TEMPLATE" > "$RENDERED"

mkdir -p "$HOME/Library/LaunchAgents"
ln -sf "$RENDERED" "$TARGET_PLIST"

launchctl unload "$TARGET_PLIST" 2>/dev/null || true
launchctl load "$TARGET_PLIST"

echo "[✓] Đã cài $LABEL"
echo "    Python:  $PYTHON_BIN"
echo "    Workdir: $REPO_DIR"
echo "    Time:    $(printf '%02d:%02d' "$HOUR" "$MINUTE") hằng ngày"
echo "    Logs:    $REPO_DIR/launchd/sync.{out,err}.log"
echo ""
echo "Test ngay: launchctl start $LABEL"
