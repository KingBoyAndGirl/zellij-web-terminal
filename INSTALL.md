# Zellij Web Terminal 安装文档

> 本文档记录每一步配置，方便回滚和分享到其他机器

## 环境信息
- 系统: LightOS (懒猫微服) 沙箱
- 用户: devbox
- zellij 版本: 0.44.1 (官方版)

---

## 步骤 1: 安装官方 zellij

```bash
# 下载官方二进制
cd /tmp
curl -L "https://github.com/zellij-org/zellij/releases/download/v0.44.1/zellij-x86_64-unknown-linux-musl.tar.gz" -o zellij.tar.gz
tar xzf zellij.tar.gz

# 安装
mkdir -p ~/.local/bin
cp zellij ~/.local/bin/zellij
chmod +x ~/.local/bin/zellij

# 验证
~/.local/bin/zellij --version
```

**状态**: ✅ 完成

---

## 步骤 2: 生成 SSL 证书

```bash
mkdir -p ~/.local/share/zellij-web/certs
openssl req -x509 -newkey rsa:2048 \
  -keyout ~/.local/share/zellij-web/certs/key.pem \
  -out ~/.local/share/zellij-web/certs/cert.pem \
  -days 3650 -nodes -subj "/CN=zellij.local"
```

**状态**: ⏳ 待执行

---

## 步骤 3: 创建登录 Token

```bash
~/.local/bin/zellij web --create-token
```

记录输出的 token 值。

**状态**: ⏳ 待执行

---

## 步骤 4: 配置 proxy.py

创建 `~/.local/share/zellij-web/config/proxy.py`，内容见附件。

**状态**: ⏳ 待执行

---

## 步骤 5: 创建 systemd 服务

**zellij-web.service**:
```ini
[Unit]
Description=Zellij Web Terminal Server
After=network.target

[Service]
Type=simple
User=devbox
ExecStart=/bin/bash -l -c 'exec /home/devbox/.local/bin/zellij web --start --port 18084 --ip 127.0.0.1'
Restart=on-failure
RestartSec=5
Environment=HOME=/home/devbox

[Install]
WantedBy=multi-user.target
```

**zellij-frontend.service**:
```ini
[Unit]
Description=Zellij Gateway Proxy
After=network.target zellij-web.service

[Service]
Type=simple
User=devbox
WorkingDirectory=/home/devbox/.local/share/zellij-web/config
ExecStart=/usr/bin/python3 /home/devbox/.local/share/zellij-web/config/proxy.py
Restart=on-failure
RestartSec=3
Environment=HOME=/home/devbox

[Install]
WantedBy=multi-user.target
```

**状态**: ⏳ 待执行

---

## 步骤 6: 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zellij-web zellij-frontend
```

**状态**: ⏳ 待执行

---

## 回滚指南

如需回滚到某一步之前的状态：

```bash
# 停止服务
sudo systemctl stop zellij-web zellij-frontend

# 回滚到步骤 X 之前
# 删除对应步骤创建的文件...

# 重启服务
sudo systemctl start zellij-web zellij-frontend
```

---

## 文件清单

| 文件 | 说明 | 创建步骤 |
|------|------|----------|
| `~/.local/bin/zellij` | zellij 二进制 | 步骤 1 |
| `~/.local/share/zellij-web/certs/cert.pem` | SSL 证书 | 步骤 2 |
| `~/.local/share/zellij-web/certs/key.pem` | SSL 私钥 | 步骤 2 |
| `~/.local/share/zellij-web/config/auth_token.txt` | 登录 token | 步骤 3 |
| `~/.local/share/zellij-web/config/proxy.py` | 代理服务 | 步骤 4 |
| `/etc/systemd/system/zellij-web.service` | systemd 服务 | 步骤 5 |
| `/etc/systemd/system/zellij-frontend.service` | systemd 服务 | 步骤 5 |

---

## 步骤 7: 隐藏原生 UI (可选)

如果需要隐藏 zellij 原生的 Tab 栏和状态栏：

```bash
# 克隆源码
cd /data/code
git clone --depth 1 --branch v0.44.1 https://github.com/zellij-org/zellij.git zellij-hide-native-ui
cd zellij-hide-native-ui

# 修改默认布局，移除 tab-bar 和 status-bar
cat > zellij-utils/assets/layouts/default.kdl << 'LAYOUT'
layout {
    pane
}
LAYOUT

# 编译
cargo build --release

# 替换二进制
sudo -S -p '' systemctl stop zellij-web zellij-frontend
pkill -9 -f 'zellij'
cp ~/.local/bin/zellij ~/.local/bin/zellij.official.bak
cp target/release/zellij ~/.local/bin/zellij
chmod +x ~/.local/bin/zellij

# 重启服务
sudo -S -p '' systemctl start zellij-web zellij-frontend
```

**状态**: ✅ 完成

---

## 文件清单 (更新)

| 文件 | 说明 | 创建步骤 |
|------|------|----------|
| `~/.local/bin/zellij` | zellij 二进制 (隐藏原生UI版) | 步骤 7 |
| `~/.local/bin/zellij.official.bak` | 官方版备份 | 步骤 7 |
| `/data/code/zellij-hide-native-ui/` | 修改版源码 | 步骤 7 |
