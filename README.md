# Zellij Web Terminal - 定制化版本

基于官方 [Zellij](https://github.com/zellij-org/zellij) v0.44.1 的定制化 Web 终端，提供：
- 🎨 自定义工具栏（四行快捷按钮）
- 📑 浏览器式 Tab 栏（动态创建/切换/关闭）
- 📱 移动端适配（虚拟键盘自动调整）
- 🔐 自动认证（免输入 Token）
- 🌐 多设备共享同一终端
- ⌨️ 中文输入法支持

## 架构

```
浏览器 → HTTPS:18082 (Python Proxy) → HTTP:18084 (Zellij Web Server)
```

## 功能特性

### 自定义工具栏（四行）
```
第一行: ESC | Enter | Newline | TAB
第二行: Close | H-Split | V-Split | Fullscreen
第三行: ↑ | ↓ | ← | → | ⌫ | ⌦ | Paste | ^C
第四行: Clear | Home | History | Detach | Quit
```

### 浏览器式 Tab 栏
- 动态创建/切换/关闭 Tab
- 多设备状态同步（HTTP 轮询 600ms）
- 默认 Tab 名显示当前用户名

### 移动端适配
- 虚拟键盘弹出时工具栏自动上移
- iOS 粘贴免授权（隐藏 textarea 方案）

## 快速安装

### 方式一：一键安装脚本（推荐）

```bash
curl -sL https://raw.githubusercontent.com/KingBoyAndGirl/zellij-web-terminal/main/install.sh | bash
```

### 方式二：手动安装

```bash
# 1. 下载预编译包
wget https://github.com/KingBoyAndGirl/zellij-web-terminal/releases/latest/download/zellij-web-terminal.tar.gz
tar xzf zellij-web-terminal.tar.gz
cd zellij-web-terminal

# 2. 运行安装脚本
chmod +x install.sh
./install.sh
```

### 方式三：从源码编译

参见 [INSTALL.md](INSTALL.md)

## 文件结构

```
zellij-web-terminal/
├── bin/
│   └── zellij-customized    # 定制版 zellij 二进制
├── src/
│   └── proxy.py             # Python TLS 代理
├── config/
│   ├── zellij-web.service       # systemd 服务
│   └── zellij-frontend.service  # systemd 服务
├── install.sh               # 一键安装脚本
├── uninstall.sh             # 卸载脚本
├── INSTALL.md               # 详细安装文档
└── README.md                # 本文件
```

## 管理命令

```bash
# 查看状态
sudo systemctl status zellij-web zellij-frontend

# 重启服务
sudo systemctl restart zellij-web zellij-frontend

# 查看日志
sudo journalctl -u zellij-web -f
sudo journalctl -u zellij-frontend -f

# 检查端口
ss -tlnp | grep -E '18082|18084'
```

## 定制化内容

相对于官方 Zellij v0.44.1，本项目做了以下定制：

| 改动 | 文件 | 说明 |
|------|------|------|
| UI 注入 | `src/proxy.py` | 通过 TLS 代理注入自定义工具栏和 Tab 栏 |
| WebSocket 拦截 | `src/proxy.py` | 强制所有设备连接同一 session |
| 自动认证 | `src/proxy.py` | 拦截登录请求，自动填充 Token |
| Tab 状态同步 | `src/proxy.py` | HTTP API 实现多设备 Tab 状态同步 |
| 移动端适配 | `src/proxy.py` | visualViewport API 检测虚拟键盘 |

## 许可证

MIT License

## 致谢

- [Zellij](https://github.com/zellij-org/zellij) - 原始项目
- [xterm.js](https://github.com/xtermjs/xterm.js) - Web 终端组件

## v0.1.1 更新

- ✅ 隐藏原生 Tab 栏和状态栏
- ✅ 修改所有布局文件（default/compact/classic/strider）
