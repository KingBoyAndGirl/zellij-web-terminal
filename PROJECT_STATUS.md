# Zellij Web 终端项目 - 未完成

## 当前状态
- Zellij v0.44.1 已安装: `/home/devbox/.local/bin/zellij`
- 配置: `~/.config/zellij/config.kdl`
- 自定义主题: `~/.config/zellij/themes/white-jade.kdl` (XTerm 配色)
- TLS 证书: `~/.config/zellij/cert.pem` / `key.pem` (自签名, 到2036年)

## 用户最终需求（未实现）
1. **多设备共享**: 所有设备访问 `https://zellij.nasw.heiyu.space/` 看到同一个终端，操作实时同步
2. **手机快捷按钮**: 复制、粘贴、回车、换行、方向键、ESC、^C 等
3. **PC 快捷键**: Shift+Enter / Alt+Enter 换行
4. **中文输入法不重复**: "您好" 不应显示为 "您好您好"
5. **环境变量继承**: shell 应继承用户完整环境
6. **所有设备同一配色**: XTerm 风格，黑底白字

## 当前架构（有问题）
```
18082 (0.0.0.0 TLS) → Python proxy (proxy.py)
  ├── / → index.html (自定义页面, 带按钮)
  └── 其他路径 → proxy → 127.0.0.1:18084 (Zellij)
       (注入 FIX_JS_HEAD 在 <head> - 拦截 WebSocket)
       (注入 FIX_JS_BODY 在 </body> - 修复中文 IME)
```

## 已知问题
1. **按钮无效**: 尝试了多种方案都不行
   - `term.paste()` - 不处理特殊按键
   - 模拟 keydown 事件 - xterm.js 不响应合成事件
   - 拦截 WebSocket 构造函数 - 注入时序问题
   - postMessage → 注入脚本 → WebSocket.send - 按钮仍无效
2. **中文输入法重复**: compositionstart/end 修复未生效
3. **环境变量**: service 已设 Environment 但可能不完整

## 文件位置
- 代理: `/home/devbox/.config/zellij/web/proxy.py` (asyncio TLS proxy)
- 页面: `/home/devbox/.config/zellij/web/index.html` (按钮界面)
- Service: `/etc/systemd/system/zellij-web.service` (Zellij 18084)
- Service: `/etc/systemd/system/zellij-frontend.service` (代理 18082)

## 反代映射（不可改）
`https://zellij.nasw.heiyu.space/` → `https://127.0.0.1:18082/`

## 建议方案
最可靠的方案可能是：**放弃 Python 代理，直接用 Zellij 的 web server，但通过修改 Zellij 源码或使用 Nginx 反代实现自定义页面注入**。
或者：**使用 Nginx 作为本地反代，在 Nginx 层面注入 JS 和处理 WebSocket**。
