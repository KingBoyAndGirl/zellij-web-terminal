#!/bin/bash
set -e

# ============================================
# Zellij Web Terminal - 一键安装脚本
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否为 root
if [ "$EUID" -eq 0 ]; then
    log_warn "检测到 root 用户，将安装到系统目录"
    INSTALL_DIR="/opt/zellij-web"
    BIN_DIR="/usr/local/bin"
    SERVICE_DIR="/etc/systemd/system"
else
    log_info "普通用户模式，将安装到用户目录"
    INSTALL_DIR="$HOME/.local/share/zellij-web"
    BIN_DIR="$HOME/.local/bin"
    SERVICE_DIR="$HOME/.config/systemd/user"
fi

CONFIG_DIR="$INSTALL_DIR/config"
CERT_DIR="$INSTALL_DIR/certs"

log_info "=========================================="
log_info "  Zellij Web Terminal 安装程序"
log_info "=========================================="

# 1. 创建目录
log_info "[1/6] 创建安装目录..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$CERT_DIR" "$BIN_DIR"
mkdir -p "$SERVICE_DIR"

# 2. 安装 zellij 二进制
log_info "[2/6] 安装 zellij..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/bin/zellij" ]; then
    # 本地有 zellij 二进制
    cp "$SCRIPT_DIR/bin/zellij" "$BIN_DIR/zellij"
    chmod +x "$BIN_DIR/zellij"
    log_info "  已从本地安装到: $BIN_DIR/zellij"
elif [ -f "$SCRIPT_DIR/zellij-x86_64" ]; then
    # 本地有重命名的 zellij
    cp "$SCRIPT_DIR/zellij-x86_64" "$BIN_DIR/zellij"
    chmod +x "$BIN_DIR/zellij"
    log_info "  已从本地安装到: $BIN_DIR/zellij"
else
    # 从 GitHub 下载
    log_info "  本地未找到 zellij，从 GitHub 下载..."
    GITHUB_REPO="KingBoyAndGirl/zellij-web-terminal"
    LATEST_TAG=$(curl -s "https://api.github.com/repos/$GITHUB_REPO/releases/latest" | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
    
    if [ -z "$LATEST_TAG" ]; then
        LATEST_TAG="v1.0.0"
    fi
    
    DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/download/$LATEST_TAG/zellij-x86_64"
    log_info "  下载地址: $DOWNLOAD_URL"
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$BIN_DIR/zellij" "$DOWNLOAD_URL"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar -o "$BIN_DIR/zellij" "$DOWNLOAD_URL"
    else
        log_error "需要 wget 或 curl 来下载文件"
        exit 1
    fi
    
    chmod +x "$BIN_DIR/zellij"
    log_info "  已下载并安装到: $BIN_DIR/zellij"
fi

# 3. 安装 proxy.py
log_info "[3/6] 安装代理服务..."
cp "$SCRIPT_DIR/config/proxy.py" "$CONFIG_DIR/proxy.py"
log_info "  已安装到: $CONFIG_DIR/proxy.py"

# 4. 生成 SSL 证书
log_info "[4/6] 生成 SSL 证书..."
if [ ! -f "$CERT_DIR/cert.pem" ]; then
    openssl req -x509 -newkey rsa:2048 -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" -days 3650 -nodes \
        -subj "/CN=localhost" 2>/dev/null
    log_info "  证书已生成: $CERT_DIR/"
else
    log_info "  证书已存在，跳过"
fi

# 5. 生成登录 token
log_info "[5/6] 生成登录 token..."
if [ ! -f "$CONFIG_DIR/auth_token.txt" ]; then
    TOKEN=$("$BIN_DIR/zellij" web --create-token 2>/dev/null || uuidgen || cat /proc/sys/kernel/random/uuid)
    echo "$TOKEN" > "$CONFIG_DIR/auth_token.txt"
    log_info "  Token: $TOKEN"
else
    TOKEN=$(cat "$CONFIG_DIR/auth_token.txt")
    log_info "  使用已有 Token: $TOKEN"
fi

# 6. 更新 proxy.py 中的配置路径
log_info "[6/6] 配置代理服务..."
sed -i "s|AUTO_TOKEN=\".*\"|AUTO_TOKEN=\"$TOKEN\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|CERT = \".*\"|CERT = \"$CERT_DIR/cert.pem\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|KEY = \".*\"|KEY = \"$CERT_DIR/key.pem\"|g" "$CONFIG_DIR/proxy.py"
sed -i "s|WEB_DIR = \".*\"|WEB_DIR = \"$CONFIG_DIR\"|g" "$CONFIG_DIR/proxy.py"

# 创建 systemd 服务文件
log_info "创建 systemd 服务..."

# Zellij Web 服务
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

# Proxy 服务
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

# 启用并启动服务
log_info "启用服务..."
if [ "$EUID" -eq 0 ]; then
    systemctl daemon-reload
    systemctl enable zellij-web zellij-frontend
    systemctl start zellij-web zellij-frontend
else
    systemctl --user daemon-reload
    systemctl --user enable zellij-web zellij-frontend
    systemctl --user start zellij-web zellij-frontend
fi

# 完成
echo ""
log_info "=========================================="
log_info "  安装完成！"
log_info "=========================================="
echo ""
log_info "访问地址: https://$(hostname -I | awk '{print $1}' || hostname):18082"
log_info "登录 Token: $TOKEN"
echo ""
log_warn "注意："
log_warn "1. 首次访问需要接受自签名证书警告"
log_warn "2. 防火墙需开放 18082 端口"
log_warn "3. 如需修改端口，编辑 $CONFIG_DIR/proxy.py"
echo ""
log_info "管理命令："
if [ "$EUID" -eq 0 ]; then
    log_info "  查看状态: systemctl status zellij-web zellij-frontend"
    log_info "  重启服务: systemctl restart zellij-web zellij-frontend"
    log_info "  查看日志: journalctl -u zellij-frontend -f"
else
    log_info "  查看状态: systemctl --user status zellij-web zellij-frontend"
    log_info "  重启服务: systemctl --user restart zellij-web zellij-frontend"
    log_info "  查看日志: journalctl --user -u zellij-frontend -f"
fi
echo ""
