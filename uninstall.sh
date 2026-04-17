#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${RED}[WARN]${NC} $1"; }

if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR="/opt/zellij-web"
    BIN_DIR="/usr/local/bin"
    SERVICE_DIR="/etc/systemd/system"
else
    INSTALL_DIR="$HOME/.local/share/zellij-web"
    BIN_DIR="$HOME/.local/bin"
    SERVICE_DIR="$HOME/.config/systemd/user"
fi

log_warn "这将卸载 Zellij Web Terminal"
read -p "确定要继续吗？(y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "已取消"
    exit 0
fi

log_info "停止服务..."
if [ "$EUID" -eq 0 ]; then
    systemctl stop zellij-web zellij-frontend 2>/dev/null || true
    systemctl disable zellij-web zellij-frontend 2>/dev/null || true
    rm -f "$SERVICE_DIR/zellij-web.service" "$SERVICE_DIR/zellij-frontend.service"
    systemctl daemon-reload
else
    systemctl --user stop zellij-web zellij-frontend 2>/dev/null || true
    systemctl --user disable zellij-web zellij-frontend 2>/dev/null || true
    rm -f "$SERVICE_DIR/zellij-web.service" "$SERVICE_DIR/zellij-frontend.service"
    systemctl --user daemon-reload
fi

log_info "删除文件..."
rm -f "$BIN_DIR/zellij"
rm -rf "$INSTALL_DIR"

log_info "卸载完成！"
