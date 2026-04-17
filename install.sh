#!/bin/bash
# Zellij Web Terminal - 一键安装脚本
# 用法: curl -sL https://raw.githubusercontent.com/KingBoyAndGirl/zellij-web-terminal/main/install.sh | bash

set -e

echo "🚀 Zellij Web Terminal 安装脚本"
echo "================================"

# 配置
INSTALL_DIR="$HOME/.local/share/zellij-web"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$INSTALL_DIR/config"
CERT_DIR="$INSTALL_DIR/certs"
REPO_URL="https://github.com/KingBoyAndGirl/zellij-web-terminal"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

# 检查依赖
check_deps() {
    echo "检查依赖..."
    
    if ! command -v python3 &> /dev/null; then
        error "Python3 未安装"
    fi
    
    if ! command -v openssl &> /dev/null; then
        error "OpenSSL 未安装"
    fi
    
    if ! command -v curl &> /dev/null; then
        error "curl 未安装"
    fi
    
    info "依赖检查通过"
}

# 创建目录
create_dirs() {
    echo "创建目录..."
    mkdir -p "$BIN_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$CERT_DIR"
    info "目录创建完成"
}

# 下载 zellij 二进制
download_zellij() {
    echo "下载 zellij..."
    
    # 如果已存在定制版，跳过
    if [ -f "$BIN_DIR/zellij" ]; then
        warn "zellij 已存在，跳过下载"
        return
    fi
    
    # 尝试下载预编译包
    if command -v wget &> /dev/null; then
        wget -q "${REPO_URL}/releases/latest/download/zellij-customized" -O "$BIN_DIR/zellij" 2>/dev/null
    else
        curl -sL "${REPO_URL}/releases/latest/download/zellij-customized" -o "$BIN_DIR/zellij" 2>/dev/null
    fi
    
    # 如果下载失败，使用官方版本
    if [ ! -f "$BIN_DIR/zellij" ] || [ ! -s "$BIN_DIR/zellij" ]; then
        warn "预编译包下载失败，使用官方版本"
        
        # 检测架构
        ARCH=$(uname -m)
        case $ARCH in
            x86_64) ZELLIJ_ARCH="x86_64-unknown-linux-musl" ;;
            aarch64) ZELLIJ_ARCH="aarch64-unknown-linux-musl" ;;
            *) error "不支持的架构: $ARCH" ;;
        esac
        
        # 下载官方版本
        TMPDIR=$(mktemp -d)
        cd "$TMPDIR"
        
        if command -v wget &> /dev/null; then
            wget -q "https://github.com/zellij-org/zellij/releases/download/v0.44.1/zellij-${ZELLIJ_ARCH}.tar.gz" -O zellij.tar.gz
        else
            curl -sL "https://github.com/zellij-org/zellij/releases/download/v0.44.1/zellij-${ZELLIJ_ARCH}.tar.gz" -o zellij.tar.gz
        fi
        
        tar xzf zellij.tar.gz
        cp zellij "$BIN_DIR/zellij"
        cd -
        rm -rf "$TMPDIR"
    fi
    
    chmod +x "$BIN_DIR/zellij"
    info "zellij 下载完成"
}

# 生成 SSL 证书
generate_cert() {
    echo "生成 SSL 证书..."
    
    if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
        warn "SSL 证书已存在，跳过生成"
        return
    fi
    
    openssl req -x509 -newkey rsa:2048 \
        -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" \
        -days 3650 -nodes \
        -subj "/CN=zellij.local" 2>/dev/null
    
    info "SSL 证书生成完成"
}

# 创建登录 Token
create_token() {
    echo "创建登录 Token..."
    
    if [ -f "$CONFIG_DIR/auth_token.txt" ]; then
        warn "Token 已存在，跳过创建"
        return
    fi
    
    # 创建 session
    echo 'exit' | "$BIN_DIR/zellij" --session install 2>/dev/null || true
    
    # 创建 token
    TOKEN_OUTPUT=$("$BIN_DIR/zellij" web --create-token 2>&1)
    TOKEN=$(echo "$TOKEN_OUTPUT" | grep -oP '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' | tail -1)
    
    if [ -z "$TOKEN" ]; then
        # 如果无法创建 token，生成一个随机的
        TOKEN=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")
    fi
    
    echo "$TOKEN" > "$CONFIG_DIR/auth_token.txt"
    info "Token 创建完成: $TOKEN"
}

# 下载 proxy.py
download_proxy() {
    echo "下载 proxy.py..."
    
    if [ -f "$CONFIG_DIR/proxy.py" ]; then
        warn "proxy.py 已存在，跳过下载"
        return
    fi
    
    # 读取 token
    TOKEN=$(cat "$CONFIG_DIR/auth_token.txt")
    
    # 下载 proxy.py 模板
    if command -v wget &> /dev/null; then
        wget -q "${REPO_URL}/raw/main/src/proxy.py" -O "$CONFIG_DIR/proxy.py" 2>/dev/null
    else
        curl -sL "${REPO_URL}/raw/main/src/proxy.py" -o "$CONFIG_DIR/proxy.py" 2>/dev/null
    fi
    
    # 如果下载失败，使用内置模板
    if [ ! -f "$CONFIG_DIR/proxy.py" ] || [ ! -s "$CONFIG_DIR/proxy.py" ]; then
        warn "proxy.py 下载失败，请手动配置"
        return
    fi
    
    # 替换配置
    sed -i "s|AUTO_TOKEN = \".*\"|AUTO_TOKEN = \"$TOKEN\"|g" "$CONFIG_DIR/proxy.py"
    sed -i "s|CERT = \".*\"|CERT = \"$CERT_DIR/cert.pem\"|g" "$CONFIG_DIR/proxy.py"
    sed -i "s|KEY = \".*\"|KEY = \"$CERT_DIR/key.pem\"|g" "$CONFIG_DIR/proxy.py"
    sed -i "s|WEB_DIR = \".*\"|WEB_DIR = \"$CONFIG_DIR\"|g" "$CONFIG_DIR/proxy.py"
    
    info "proxy.py 配置完成"
}

# 创建 systemd 服务
create_services() {
    echo "创建 systemd 服务..."
    
    # zellij-web.service
    sudo tee /etc/systemd/system/zellij-web.service > /dev/null << EOF
[Unit]
Description=Zellij Web Terminal Server
After=network.target

[Service]
Type=forking
User=$USER
ExecStartPre=/bin/bash -c 'echo exit | $BIN_DIR/zellij --session web 2>/dev/null || true'
ExecStart=$BIN_DIR/zellij web --start --daemonize --port 18084 --ip 127.0.0.1
Restart=on-failure
RestartSec=5
Environment=HOME=$HOME

[Install]
WantedBy=multi-user.target
EOF

    # zellij-frontend.service
    sudo tee /etc/systemd/system/zellij-frontend.service > /dev/null << EOF
[Unit]
Description=Zellij Gateway Proxy
After=network.target zellij-web.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$CONFIG_DIR
ExecStart=/usr/bin/python3 $CONFIG_DIR/proxy.py
Restart=on-failure
RestartSec=3
Environment=HOME=$HOME

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    info "systemd 服务创建完成"
}

# 启动服务
start_services() {
    echo "启动服务..."
    
    sudo systemctl enable --now zellij-web zellij-frontend
    sleep 3
    
    # 检查状态
    if sudo systemctl is-active --quiet zellij-web && sudo systemctl is-active --quiet zellij-frontend; then
        info "服务启动成功"
    else
        warn "服务启动可能有问题，请检查日志"
        echo "  sudo journalctl -u zellij-web -n 20"
        echo "  sudo journalctl -u zellij-frontend -n 20"
    fi
}

# 显示完成信息
show_done() {
    echo ""
    echo "================================"
    echo -e "${GREEN}🎉 安装完成！${NC}"
    echo "================================"
    echo ""
    echo "访问地址: https://$(hostname -I | awk '{print $1}'):18082"
    echo ""
    echo "管理命令:"
    echo "  sudo systemctl status zellij-web zellij-frontend"
    echo "  sudo systemctl restart zellij-web zellij-frontend"
    echo "  sudo journalctl -u zellij-frontend -f"
    echo ""
    echo "Token 文件: $CONFIG_DIR/auth_token.txt"
    echo ""
}

# 主函数
main() {
    check_deps
    create_dirs
    download_zellij
    generate_cert
    create_token
    download_proxy
    create_services
    start_services
    show_done
}

# 运行
main
