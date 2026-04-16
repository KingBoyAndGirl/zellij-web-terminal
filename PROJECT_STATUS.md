# Zellij Web 终端项目 - ✅ 已完成

## 当前状态
- Zellij v0.44.1 已安装: `/home/devbox/.local/bin/zellij`
- 配置: `~/.config/zellij/config.kdl`
- 自定义主题: `~/.config/zellij/themes/white-jade.kdl` (XTerm 配色)
- TLS 证书: `~/.config/zellij/cert.pem` / `key.pem` (自签名, 到2036年)

## 用户最终需求（已实现）✅
1. **多设备共享**: ✅ 所有设备访问 `https://zellij.nasw.heiyu.space/` 看到同一个终端（session: "default"），操作实时同步
2. **手机快捷按钮**: ✅ 复制、粘贴、回车、换行、方向键、ESC、^C 等
3. **PC 快捷键**: ✅ Shift+Enter / Alt+Enter 换行
4. **中文输入法不重复**: ✅ xterm.js 原生 composition 事件处理 + ws.send 去重
5. **粘贴不重复**: ✅ 移除自定义粘贴拦截，Zellij ClipboardAddon 原生处理 + ws.send 去重 (2026-04-16)
6. **环境变量继承**: ✅ `bash -l -c` 加 PATH 环境变量
7. **所有设备同一配色**: ✅ XTerm 风格，黑底白字
8. **免认证**: ✅ 代理自动拦截 /command/login 和 /session
9. **苹果粘贴免授权**: ✅ 隐藏 textarea + paste 事件监听

## 当前架构
```
浏览器 → https://zellij.nasw.heiyu.space/
  → 反代 → https://127.0.0.1:18082 (proxy.py, asyncio TLS)
    ├── GET / → 注入 UI 到 Zellij /shared 页面
    ├── POST /command/login → 自动 token 登录
    ├── POST /session → 自动获取 web_client_id
    └── WebSocket → proxy → Zellij (/ws/terminal/default)
    
注入内容:
  - <head>: CSS 工具栏样式
  - <body>: sessionName="default" + WS拦截 + 自动登录 + 按钮HTML + 按钮JS
  - CSP: 修改为 'unsafe-inline' 允许内联脚本执行
```

## 关键发现
1. **CSP 阻止内联脚本**: Zellij 返回 `Content-Security-Policy: default-src 'self'`，禁止所有 `<script>...</script>` 内联脚本执行。必须在代理中修改 CSP 为 `'unsafe-inline'` 才能让注入的 JS 运行。这是调试过程中最大的坑。
2. **Zellij 内置 ClipboardAddon**: Zellij web client 使用 `@xterm/addon-clipboard` 处理粘贴。input.js 的 `attachCustomKeyEventHandler` 将 Cmd+V/Ctrl+Shift+V pass-through 给 xterm.js，ClipboardAddon 自动处理剪贴板读取 → `onData` → `sendFunction` → `ws.send`。不需要自定义粘贴拦截。如果自定义拦截，会导致两条路径同时发送相同数据（重复）。

## 文件位置
- 代理: `/home/devbox/.config/zellij/web/proxy.py` (asyncio TLS proxy + 注入)
- 页面: `/home/devbox/.config/zellij/web/index.html` (备用，当前未使用)
- 服务: `/etc/systemd/system/zellij-web.service` (Zellij 18084)
- 服务: `/etc/systemd/system/zellij-frontend.service` (代理 18082)

## 反代映射
`https://zellij.nasw.heiyu.space/` → `https://127.0.0.1:18082/`

## Token
AUTO_TOKEN = `f48eed44-0fbe-4eba-a966-5ccaee873bc9` (通过 `zellij web --create-token` 创建)
