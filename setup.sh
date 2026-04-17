#!/bin/bash
set -e

# ============================================
# Zellij Web Terminal - 一键安装脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/KingBoyAndGirl/zellij-web-terminal/main/setup.sh | bash
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }

GITHUB_REPO="KingBoyAndGirl/zellij-web-terminal"
GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_REPO/main"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                        ║${NC}"
echo -e "${BLUE}║       Zellij Web Terminal - 一键安装程序               ║${NC}"
echo -e "${BLUE}║                                                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查系统
log_step "检查系统环境..."
if [[ "$(uname)" != "Linux" ]]; then
    log_error "仅支持 Linux 系统"
    exit 1
fi

if [[ "$(uname -m)" != "x86_64" ]]; then
    log_error "仅支持 x86_64 架构"
    exit 1
fi

# 检查依赖
for cmd in python3 openssl curl; do
    if ! command -v $cmd &> /dev/null; then
        log_error "缺少依赖: $cmd"
        exit 1
    fi
done
log_info "系统检查通过"

# 确定安装目录
if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR="/opt/zellij-web"
    BIN_DIR="/usr/local/bin"
    SERVICE_DIR="/etc/systemd/system"
    IS_ROOT=true
    log_warn "检测到 root 用户，将安装到系统目录"
else
    INSTALL_DIR="$HOME/.local/share/zellij-web"
    BIN_DIR="$HOME/.local/bin"
    SERVICE_DIR="$HOME/.config/systemd/user"
    IS_ROOT=false
fi

CONFIG_DIR="$INSTALL_DIR/config"
CERT_DIR="$INSTALL_DIR/certs"

# 确认安装
read -p "确认安装到 $INSTALL_DIR ? (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "已取消"
    exit 0
fi

# 1. 创建目录
log_step "创建安装目录..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$CERT_DIR" "$BIN_DIR"
mkdir -p "$SERVICE_DIR"
log_info "目录创建完成"

# 2. 下载 zellij
log_step "下载 Zellij (修改版，修复 IME 重复)..."
LATEST_TAG=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
if [ -z "$LATEST_TAG" ]; then
    LATEST_TAG="v1.0.0"
fi
ZELLIJ_URL="https://github.com/$GITHUB_REPO/releases/download/$LATEST_TAG/zellij-x86_64"
log_info "版本: $LATEST_TAG"

curl -L --progress-bar -o "$BIN_DIR/zellij" "$ZELLIJ_URL"
chmod +x "$BIN_DIR/zellij"
log_info "Zellij 已安装到: $BIN_DIR/zellij"

# 3. 下载 proxy.py
log_step "下载代理服务..."
curl -sL "$GITHUB_RAW/proxy.py" -o "$CONFIG_DIR/proxy.py"
log_info "代理服务已安装到: $CONFIG_DIR/proxy.py"

# 4. 生成 SSL 证书
log_step "生成 SSL 证书..."
openssl req -x509 -newkey rsa:2048 -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" -days 3650 -nodes \
    -subj "/CN=localhost" 2>/dev/null
log_info "证书已生成: $CERT_DIR/"

# 5. 生成登录 Token
log_step "生成登录 Token..."
TOKEN=$("$BIN_DIR/zellij" web --create-token 2>/dev/null || cat /proc/sys/kernel/random/uuid)
echo "$TOKEN" > "$CONFIG_DIR/auth_token.txt"
log_info "Token: $TOKEN"

# 6. 配置 proxy.py
log_step "配置代理服务..."
sed -i "s|AUTO_TOKEN=\".*\"|AUTO_TOKEN=\"$TOKEN\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|CERT = \".*\"|CERT = \"$CERT_DIR/cert.pem\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|KEY = \".*\"|KEY = \"$CERT_DIR/key.pem\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|WEB_DIR = \".*\"|WEB_DIR = \"$CONFIG_DIR\"|g" "$CONFIG_DIR/proxy.py"
log_info "配置完成"

# 7. 创建 systemd 服务
log_step "创建系统服务..."

cat > "$SERVICE_DIR/zellij-web.service" << EOF
[Unit]
Description=Zellij Web Server
After=network.target

[Service]
Type=simple
ExecStart=$BIN_DIR/zellij web --start --port 18084 --ip 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

cat > "$SERVICE_DIR/zellij-frontend.service" << EOF
[Unit]
Description=Zellij Web Gateway
After=network.target zellij-web.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $CONFIG_DIR/proxy.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

log_info "服务文件已创建"

# 8. 启动服务
log_step "启动服务..."
if [ "$IS_ROOT" = true ]; then
    systemctl daemon-reload
    systemctl enable zellij-web zellij-frontend
    systemctl start zellij-web zellij-frontend
    STATUS_CMD="systemctl status zellij-web zellij-frontend"
    RESTART_CMD="systemctl restart zellij-web zellij-frontend"
    LOG_CMD="journalctl -u zellij-frontend -f"
else
    systemctl --user daemon-reload
    systemctl --user enable zellij-web zellij-frontend
    systemctl --user start zellij-web zellij-frontend
    STATUS_CMD="systemctl --user status zellij-web zellij-frontend"
    RESTART_CMD="systemctl --user restart zellij-web zellij-frontend"
    LOG_CMD="journalctl --user -u zellij-frontend -f"
    
    # 启用 linger 使用户服务开机启动
    if command -v loginctl &> /dev/null; then
        sudo loginctl enable-linger $USER 2>/dev/null || true
    fi
fi
log_info "服务已启动"

# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(hostname)
fi

# 完成
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                        ║${NC}"
echo -e "${GREEN}║              🎉 安装成功！                             ║${NC}"
echo -e "${GREEN}║                                                        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}访问地址:${NC}  https://$SERVER_IP:18082"
echo -e "  ${BLUE}登录Token:${NC} $TOKEN"
echo ""
echo -e "  ${YELLOW}注意：${NC}"
echo -e "  1. 首次访问需接受自签名证书警告"
echo -e "  2. 如无法访问，请检查防火墙是否开放 18082 端口"
echo ""
echo -e "  ${BLUE}管理命令：${NC}"
echo -e "  查看状态: $STATUS_CMD"
echo -e "  重启服务: $RESTART_CMD"
echo -e "  查看日志: $LOG_CMD"
echo ""
