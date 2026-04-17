#!/bin/bash
# Zellij Web Terminal - 发布脚本
# 用法: ./release.sh <version>

set -e

VERSION=${1:-"v0.1.0"}
REPO="KingBoyAndGirl/zellij-web-terminal"

echo "📦 发布 Zellij Web Terminal $VERSION"
echo "================================"

# 检查 gh CLI
if ! command -v gh &> /dev/null; then
    echo "❌ 需要安装 GitHub CLI (gh)"
    exit 1
fi

# 检查是否已登录
if ! gh auth status &> /dev/null; then
    echo "❌ 请先登录 GitHub CLI: gh auth login"
    exit 1
fi

# 准备发布文件
echo "准备发布文件..."
RELEASE_DIR="/tmp/zellij-web-terminal-release"
rm -rf "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

# 复制文件
cp -r src/ "$RELEASE_DIR/"
cp -r config/ "$RELEASE_DIR/"
cp -r bin/ "$RELEASE_DIR/"
cp install.sh "$RELEASE_DIR/"
cp uninstall.sh "$RELEASE_DIR/"
cp README.md "$RELEASE_DIR/"
cp INSTALL.md "$RELEASE_DIR/"

# 复制定制版 zellij
cp ~/.local/bin/zellij "$RELEASE_DIR/bin/zellij-customized"

# 创建压缩包
cd /tmp
tar czf "zellij-web-terminal-${VERSION}.tar.gz" -C "$RELEASE_DIR" .

echo "✅ 发布文件已创建: /tmp/zellij-web-terminal-${VERSION}.tar.gz"

# 创建 GitHub Release
echo "创建 GitHub Release..."
gh release create "$VERSION" \
    --repo "$REPO" \
    --title "Zellij Web Terminal $VERSION" \
    --notes "## Zellij Web Terminal $VERSION

### 功能特性
- 🎨 自定义工具栏（四行快捷按钮）
- 📑 浏览器式 Tab 栏（动态创建/切换/关闭）
- 📱 移动端适配（虚拟键盘自动调整）
- 🔐 自动认证（免输入 Token）
- 🌐 多设备共享同一终端
- ⌨️ 中文输入法支持

### 安装方式

**一键安装:**
\`\`\`bash
curl -sL https://raw.githubusercontent.com/$REPO/main/install.sh | bash
\`\`\`

**手动安装:**
\`\`\`bash
wget https://github.com/$REPO/releases/download/$VERSION/zellij-web-terminal-${VERSION}.tar.gz
tar xzf zellij-web-terminal-${VERSION}.tar.gz
cd zellij-web-terminal
chmod +x install.sh
./install.sh
\`\`\`

### 定制内容
- 基于官方 Zellij v0.44.1
- Python TLS 代理注入自定义 UI
- WebSocket 拦截实现多设备共享
- HTTP API 实现 Tab 状态同步" \
    "/tmp/zellij-web-terminal-${VERSION}.tar.gz#zellij-web-terminal-${VERSION}.tar.gz"

echo ""
echo "🎉 发布完成！"
echo "https://github.com/$REPO/releases/tag/$VERSION"
