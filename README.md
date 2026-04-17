# Zellij Web Terminal

基于 Zellij 的 Web 终端，支持：
- 🌐 浏览器访问，随时随地连接
- 📱 移动端适配，虚拟键盘自动调整
- 🎨 自定义工具栏，常用快捷键一键触发
- 🔐 自动登录，无需每次输入密码
- 📑 多 Tab 支持，多设备同步

## 快速安装

### 1. 下载并解压

```bash
# 下载（替换为实际下载链接）
wget https://example.com/zellij-web-terminal-dist.tar.gz
tar -xzf zellij-web-terminal-dist.tar.gz
cd zellij-web-terminal-dist
```

### 2. 运行安装脚本

```bash
# 普通用户安装
bash install.sh

# 或者 root 用户安装（系统级）
sudo bash install.sh
```

### 3. 访问

安装完成后，打开浏览器访问：

```
https://YOUR_SERVER_IP:18082
```

首次访问需接受自签名证书警告。

## 系统要求

- Linux x86_64 (Ubuntu/Debian/CentOS 等)
- Python 3.8+
- OpenSSL (用于生成证书)

## 手动安装

如果自动安装失败，可手动配置：

### 1. 安装 zellij

```bash
cp bin/zellij ~/.local/bin/
chmod +x ~/.local/bin/zellij
```

### 2. 配置代理

```bash
mkdir -p ~/.local/share/zellij-web/{config,certs}
cp config/proxy.py ~/.local/share/zellij-web/config/

# 生成证书
openssl req -x509 -newkey rsa:2048 -keyout ~/.local/share/zellij-web/certs/key.pem \
    -out ~/.local/share/zellij-web/certs/cert.pem -days 3650 -nodes -subj "/CN=localhost"

# 生成 token
zellij web --create-token > ~/.local/share/zellij-web/config/auth_token.txt
```

### 3. 启动服务

```bash
# 启动 Zellij Web 服务器
zellij web --start --port 18084 --ip 127.0.0.1 &

# 启动代理
python3 ~/.local/share/zellij-web/config/proxy.py &
```

### 4. 配置 systemd（可选）

参考安装脚本生成的 systemd 服务文件。

## 配置说明

### 修改端口

编辑 `proxy.py`，修改：

```python
LISTEN_PORT = 18082  # 修改为你的端口
```

### 修改认证 Token

编辑 `proxy.py`，修改：

```python
AUTO_TOKEN="your-token-here"
```

### 防火墙配置

```bash
# Ubuntu/Debian
sudo ufw allow 18082/tcp

# CentOS
sudo firewall-cmd --permanent --add-port=18082/tcp
sudo firewall-cmd --reload
```

## 工具栏按钮说明

```
第一行：ESC | Enter | Newline | TAB
第二行：Close | H-Split | V-Split | Fullscreen
第三行：↑ | ↓ | ← | → | ⌫ | ⌦ | Paste | ^C
第四行：Clear | Home | History | Detach | Quit
```

### 按钮功能

| 按钮 | 功能 |
|------|------|
| ESC | 发送 ESC 键 |
| Enter | 回车执行 |
| Newline | 换行（ESC+Enter，vim 编辑用）|
| TAB | 展开/收起编辑面板 |
| Close | 关闭当前面板（ESC+x）|
| H-Split | 水平分屏（ESC+h）|
| V-Split | 垂直分屏（ESC+v）|
| Fullscreen | 全屏切换（ESC+f）|
| ⌫ | 退格键 |
| ⌦ | 删除键 |
| Paste | 粘贴剪贴板内容 |
| ^C | Ctrl+C 中断 |
| Clear | 清屏 |
| Home | cd ~ 回到主目录 |
| History | 显示最近 20 条命令 |
| Detach | 断开会话（可重连）|
| Quit | 退出 Zellij |

## 常见问题

### Q: 无法访问页面？

1. 检查服务状态：`systemctl status zellij-web zellij-frontend`
2. 检查端口是否开放：`ss -tlnp | grep 18082`
3. 检查防火墙配置

### Q: 中文输入法重复？

这是已修复的问题，使用本仓库提供的修改版 zellij 即可。

### Q: 手机端键盘遮挡？

已适配，键盘弹出时工具栏会自动上移到键盘上方。

### Q: 如何修改工具栏？

编辑 `proxy.py` 中的 `INJECT_HTML` 变量。

## 技术架构

```
┌─────────────────────────────────────────────┐
│  Browser                                     │
│    ↓ HTTPS (18082)                           │
┌─────────────────────────────────────────────┐
│  Python Proxy (proxy.py)                     │
│    - 自动登录                                │
│    - 注入自定义 UI                           │
│    - 移动端键盘适配                          │
│    ↓ HTTP (18084)                            │
┌─────────────────────────────────────────────┐
│  Zellij Web Server (修改版)                  │
│    - IME 输入法修复                          │
│    - WebSocket 终端连接                      │
└─────────────────────────────────────────────┘
```

## 许可证

Zellij 采用 MIT 许可证。
本项目的 UI 定制部分同样采用 MIT 许可证。

## 相关链接

- Zellij 官方：https://zellij.dev
- 本项目 GitHub：https://github.com/KingBoyAndGirl/zellij-web-terminal
