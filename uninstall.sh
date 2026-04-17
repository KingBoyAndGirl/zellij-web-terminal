#!/bin/bash
# Zellij Web Terminal - 卸载脚本

set -e

echo "🗑️  Zellij Web Terminal 卸载脚本"
echo "================================"

# 配置
INSTALL_DIR="$HOME/.local/share/zellij-web"
BIN_DIR="$HOME/.local/bin"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# 停止服务
stop_services() {
    echo "停止服务..."
    
    if systemctl is-active --quiet zellij-web 2>/dev/null; then
        sudo systemctl stop zellij-web
    fi
    
    if systemctl is-active --quiet zellij-frontend 2>/dev/null; then
        sudo systemctl stop zellij-frontend
    fi
    
    # 杀掉所有 zellij 进程
    pkill -9 -f 'zellij' 2>/dev/null || true
    pkill -9 -f 'proxy.py' 2>/dev/null || true
    
    info "服务已停止"
}

# 禁用并删除 systemd 服务
remove_services() {
    echo "删除 systemd 服务..."
    
    sudo systemctl disable zellij-web 2>/dev/null || true
    sudo systemctl disable zellij-frontend 2>/dev/null || true
    
    sudo rm -f /etc/systemd/system/zellij-web.service
    sudo rm -f /etc/systemd/system/zellij-frontend.service
    
    sudo systemctl daemon-reload
    
    info "systemd 服务已删除"
}

# 删除文件
remove_files() {
    echo "删除文件..."
    
    # 备份 zellij 二进制（如果是定制版）
    if [ -f "$BIN_DIR/zellij" ]; then
        mv "$BIN_DIR/zellij" "$BIN_DIR/zellij.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    fi
    
    # 删除配置目录
    rm -rf "$INSTALL_DIR"
    
    info "文件已删除"
}

# 确认卸载
confirm() {
    echo ""
    warn "此操作将完全卸载 Zellij Web Terminal"
    echo ""
    read -p "确认卸载? (y/N) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消卸载"
        exit 0
    fi
}

# 显示完成信息
show_done() {
    echo ""
    echo "================================"
    echo -e "${GREEN}🎉 卸载完成！${NC}"
    echo "================================"
    echo ""
    echo "zellij 二进制已备份到: $BIN_DIR/zellij.bak.*"
    echo ""
}

# 主函数
main() {
    confirm
    stop_services
    remove_services
    remove_files
    show_done
}

# 运行
main
