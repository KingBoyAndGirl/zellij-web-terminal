#!/usr/bin/env python3
"""Zellij Gateway - TLS on 18082, proxy to Zellij on 18084"""
import asyncio
import ssl
import os
import json
import re
import threading
import sys
from typing import Optional

# 配置
ZELLIJ = "127.0.0.1"
ZELLIJ_PORT = 18084
LISTEN_PORT = 18082
AUTO_TOKEN = "25008711-f1d7-47f8-be7e-de18a1f2b057"
CERT = os.path.expanduser("~/.local/share/zellij-web/certs/cert.pem")
KEY = os.path.expanduser("~/.local/share/zellij-web/certs/key.pem")
WEB_DIR = os.path.expanduser("~/.local/share/zellij-web/config")
TAB_STATE_FILE = os.path.join(WEB_DIR, "tab_state.json")

# 获取用户名
CURRENT_USER = os.environ.get("USER", os.environ.get("LOGNAME", "user"))

# Tab 状态管理
_tab_lock = threading.Lock()

def read_tab_state() -> dict:
    try:
        with open(TAB_STATE_FILE, "r") as f:
            state = json.load(f)
        if "names" not in state:
            state["names"] = [CURRENT_USER] * state.get("count", 1)
        if "sessions" not in state:
            # 为每个 Tab 生成 session 名称
            state["sessions"] = [f"tab-{i+1}" for i in range(state.get("count", 1))]
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"count": 1, "active": 0, "names": [CURRENT_USER], "sessions": ["tab-1"], "ts": 0}

def write_tab_state(count: int, active: int, names: list = None, sessions: list = None) -> dict:
    import time
    count = max(1, count)
    active = max(0, min(active, count - 1))
    if names is None:
        old = read_tab_state()
        old_names = old.get("names", [])
        names = []
        for i in range(count):
            if i < len(old_names):
                names.append(old_names[i])
            else:
                names.append(CURRENT_USER)
    else:
        names = names[:count] + [CURRENT_USER] * max(0, count - len(names))
    
    if sessions is None:
        old = read_tab_state()
        old_sessions = old.get("sessions", [])
        sessions = []
        for i in range(count):
            if i < len(old_sessions):
                sessions.append(old_sessions[i])
            else:
                sessions.append(f"tab-{i+1}")
    else:
        sessions = sessions[:count] + [f"tab-{i+1}" for i in range(len(sessions), count)]
    
    state = {"count": count, "active": active, "names": names, "sessions": sessions, "ts": time.time()}
    with _tab_lock:
        with open(TAB_STATE_FILE, "w") as f:
            json.dump(state, f)
    return state

# 初始化 tab state 文件
if not os.path.exists(TAB_STATE_FILE):
    write_tab_state(1, 0)

# CSS 注入
INJECT_CSS = """<style>
#tab-bar {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 36px;
    background: #0d1117;
    border-bottom: 1px solid #333;
    display: flex;
    align-items: flex-end;
    padding: 0 0 0 4px;
    z-index: 999;
    overflow-x: auto;
    overflow-y: hidden;
}
#tab-bar::-webkit-scrollbar { display: none; }
#tab-list {
    display: flex;
    align-items: flex-end;
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
    gap: 1px;
    height: 100%;
}
#tab-list::-webkit-scrollbar { display: none; }
#tab-list .tab-item {
    flex: 0 1 160px;
    min-width: 80px;
    max-width: 160px;
    height: 30px;
    display: flex;
    align-items: center;
    padding: 0 6px 0 12px;
    background: #1c2028;
    border: 1px solid #333;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
    transition: background 0.15s;
    position: relative;
    top: 1px;
}
#tab-list .tab-item:hover { background: #252b36; }
#tab-list .tab-item.active {
    background: #0d1117;
    border-color: #61afef;
    border-bottom: 1px solid #0d1117;
    z-index: 1;
}
#tab-list .tab-item .tab-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 12px;
    color: #8b949e;
    line-height: 1;
}
#tab-list .tab-item.active .tab-name { color: #e6edf3; font-weight: 500; }
#tab-list .tab-item .tab-close {
    flex: 0 0 16px;
    width: 16px;
    height: 16px;
    margin-left: 4px;
    border: none;
    border-radius: 3px;
    background: transparent;
    color: #484f58;
    font-size: 14px;
    line-height: 16px;
    text-align: center;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    opacity: 0;
    transition: opacity 0.15s, background 0.15s;
}
#tab-list .tab-item:hover .tab-close { opacity: 1; }
#tab-list .tab-item.active .tab-close { opacity: 1; color: #8b949e; }
#tab-list .tab-item .tab-close:hover { background: #333; color: #f85149; }
.tab-btn-new {
    flex: 0 0 28px;
    width: 28px;
    height: 28px;
    margin: auto 4px 2px 4px;
    border: 1px solid #333;
    border-radius: 6px;
    background: transparent;
    color: #484f58;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    user-select: none;
    -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
    transition: background 0.15s, color 0.15s;
}
.tab-btn-new:hover { background: #252b36; color: #8b949e; }
.tab-btn-new:active { background: #333; color: #e6edf3; }
#term-wrap {
    position: absolute;
    top: 37px; left: 0; right: 0;
    bottom: 162px;
    background: #000;
    border: none;
    outline: none;
}
#terminal {
    width: 100%;
    height: 100%;
    border: none;
    outline: none;
    padding: 0;
    margin: 0;
}
.xterm { padding: 0; }
.xterm-viewport { overflow: hidden !important; }
#toolbar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: #111;
    border-top: 1px solid #333;
    padding: 4px 4px env(safe-area-inset-bottom, 4px);
    z-index: 999;
}
.row { display: flex; gap: 3px; margin-bottom: 3px; }
.row:last-child { margin-bottom: 0; }
.btn {
    flex: 1; height: 36px; min-width: 0;
    border: 1px solid #444; border-radius: 5px;
    background: #222; color: #ddd;
    font-size: 13px; font-weight: 500;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    user-select: none; -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
}
.btn:active { background: #555; color: #fff; }
.btn.bl { background: #1a3a5c; border-color: #61afef; color: #61afef; }
.btn.gn { background: #1a3a1a; border-color: #98c379; color: #98c379; }
.btn.rd { background: #3a1a1a; border-color: #e06c75; color: #e06c75; }
.btn.yl { background: #3a3a1a; border-color: #e5c07b; color: #e5c07b; }
html { touch-action: manipulation; }
body { margin: 0; padding: 0; overflow: hidden; }
#paste-helper {
    position: fixed;
    left: -9999px;
    top: 0;
    width: 1px;
    height: 1px;
    opacity: 0;
}
</style>"""

# WebSocket 拦截脚本
INJECT_WS_INTERCEPT = """<script>
(function() {
    var OriginalWebSocket = window.WebSocket;
    window._termWs = null;
    window._ctrlWs = null;
    window.sessionName = window.sessionName || 'default';
    
    window.WebSocket = function(url, protocols) {
        if (url.indexOf('/ws/terminal') > -1) {
            var parsed = new URL(url, window.location.origin);
            var path = parsed.pathname;
            if (path === '/ws/terminal' || path === '/ws/terminal/') {
                parsed.pathname = '/ws/terminal/' + window.sessionName;
                url = parsed.toString();
            }
        }
        var ws = protocols ? new OriginalWebSocket(url, protocols) : new OriginalWebSocket(url);
        if (url.indexOf('/ws/terminal') > -1) {
            window._termWs = ws;
        } else if (url.indexOf('/ws/control') > -1) {
            window._ctrlWs = ws;
        }
        return ws;
    };
    window.WebSocket.CONNECTING = OriginalWebSocket.CONNECTING;
    window.WebSocket.OPEN = OriginalWebSocket.OPEN;
    window.WebSocket.CLOSING = OriginalWebSocket.CLOSING;
    window.WebSocket.CLOSED = OriginalWebSocket.CLOSED;
    
    window.__wsSend = function(data) {
        console.log("[Btn] __wsSend called:", data.substring(0, 20));
        var ws = window._termWs;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(data);
            return true;
        }
        return false;
    };
    
    window.__btnDebounce = {};
})();
</script>"""

# 自动认证脚本
INJECT_AUTH = """<script>
(function() {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/command/login', false);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.send(JSON.stringify({auth_token: '', remember_me: true}));
    if (xhr.status === 200) {
        document.body.dataset.authenticated = 'true';
    }
})();
</script>"""

# HTML 注入
INJECT_HTML = """<div id="toolbar">
    <div class="row">
        <button class="btn" id="btn-esc">ESC</button>
        <button class="btn" id="btn-enter">Enter</button>
        <button class="btn" id="btn-newline">Newline</button>
        <button class="btn bl" id="btn-edit">TAB</button>
    </div>
    <div class="row">
        <button class="btn rd" id="btn-close">Close</button>
        <button class="btn" id="btn-hsplit">H-Split</button>
        <button class="btn" id="btn-vsplit">V-Split</button>
        <button class="btn yl" id="btn-fullscreen">Fullscreen</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-up">↑</button>
        <button class="btn" id="btn-down">↓</button>
        <button class="btn" id="btn-left">←</button>
        <button class="btn" id="btn-right">→</button>
        <button class="btn" id="btn-backspace">⌫</button>
        <button class="btn" id="btn-delete">⌦</button>
        <button class="btn gn" id="btn-paste">Paste</button>
        <button class="btn rd" id="btn-ctrlc">^C</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-clear">Clear</button>
        <button class="btn" id="btn-gohome">Home</button>
        <button class="btn" id="btn-history">History</button>
        <button class="btn gn" id="btn-detach">Detach</button>
        <button class="btn rd" id="btn-quit">Quit</button>
    </div>
</div>

<div id="tab-bar">
    <div id="tab-list"></div>
    <button class="tab-btn-new" id="btn-newtab2">+</button>
</div>

"""

# JavaScript 注入模板
INJECT_JS_TEMPLATE = """<script>
(function() {
    var DEFAULT_TAB_NAME = '{username}';
    
    var term = null;
    var checkInterval = setInterval(function() {
        if (window.term) {
            term = window.term;
            clearInterval(checkInterval);
            console.log('[Hermes] Terminal ready, initializing buttons');
            init();
        }
    }, 100);
    // Fallback: after 10s, init anyway
    setTimeout(function() {
        if (!term) {
            clearInterval(checkInterval);
            term = window.term;
            console.log('[Hermes] Timeout fallback, initializing buttons');
            init();
        }
    }, 10000);

    function init() {
        var keyMap = {
            'btn-esc': '\\x1b',
            'btn-enter': '\\r',
            'btn-newline': '\\x1b\\r',
            'btn-up': '\\x1b[A',
            'btn-down': '\\x1b[B',
            'btn-left': '\\x1b[D',
            'btn-right': '\\x1b[C',
            'btn-tab': '\\t',
            'btn-backspace': '\\x7f',
            'btn-delete': '\\x1b[3~',
            'btn-ctrlc': '\\x03',
            'btn-hsplit': '\\x1bh',
            'btn-vsplit': '\\x1bv',
            'btn-fullscreen': '\\x1bf',
            'btn-close': '\\x1bx',
            'btn-detach': '\\x1bd',
            'btn-quit': '\\x1bq',
            'btn-clear': 'clear\\n',
            'btn-gohome': 'cd ~\\n',
            'btn-history': 'history | tail -20\\n'
        };

        for (var id in keyMap) {
            var btn = document.getElementById(id);
            if (btn) {
                (function(data, id) {
                    btn.addEventListener('pointerdown', function(e) {
                        e.preventDefault();
                        var now = Date.now();
                        var last = window.__btnDebounce[id] || 0;
                        if (now - last < 300) return;
                        window.__btnDebounce[id] = now;
                        if (typeof window.__wsSend === 'function') {
                            window.__wsSend(data);
                        }
                    });
                })(keyMap[id], id);
            }
        }

        // Tab 系统 - 每个 Tab 独立 session
        var tabState = { count: 1, active: 0, ts: 0, names: [], sessions: [] };
        var tabList = document.getElementById('tab-list');
        var TAB_API = '/api/tabs';

        function renderTabs() {
            if (!tabList) return;
            tabList.innerHTML = '';
            for (var i = 0; i < tabState.count; i++) {
                (function(idx) {
                    var item = document.createElement('div');
                    item.className = 'tab-item' + (idx === tabState.active ? ' active' : '');
                    var name = document.createElement('span');
                    name.className = 'tab-name';
                    name.textContent = tabState.names[idx] || DEFAULT_TAB_NAME;
                    var close = document.createElement('button');
                    close.className = 'tab-close';
                    close.textContent = '×';
                    item.appendChild(name);
                    item.appendChild(close);

                    item.addEventListener('pointerdown', function(e) {
                        if (e.target === close) return;
                        e.preventDefault();
                        var now = Date.now();
                        if (now - (window.__btnDebounce['tabclick'] || 0) < 200) return;
                        window.__btnDebounce['tabclick'] = now;
                        if (idx !== tabState.active) switchToTab(idx);
                    });

                    close.addEventListener('pointerdown', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        var now = Date.now();
                        if (now - (window.__btnDebounce['tabclose' + idx] || 0) < 300) return;
                        window.__btnDebounce['tabclose' + idx] = now;
                        closeTab(idx);
                    });

                    tabList.appendChild(item);
                })(i);
            }
            var activeEl = tabList.querySelector('.tab-item.active');
            if (activeEl) activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }

        function switchToTab(idx) {
            // 切换到对应的 session
            var sessionName = tabState.sessions[idx] || ('tab-' + (idx + 1));
            tabState.active = idx;
            saveTabState();
            // 重新加载页面到对应的 session
            window.location.href = '/?session=' + encodeURIComponent(sessionName);
        }

        function closeTab(idx) {
            if (tabState.count <= 1) return;
            var sessionToDelete = tabState.sessions[idx];
            
            // 删除 session
            fetch('/api/session/' + encodeURIComponent(sessionToDelete), {
                method: 'DELETE'
            }).catch(function(){});
            
            // 更新状态
            tabState.names.splice(idx, 1);
            tabState.sessions.splice(idx, 1);
            tabState.count--;
            
            // 确定新的 active
            var newActive;
            if (idx < tabState.active) {
                newActive = tabState.active - 1;
            } else if (idx === tabState.active) {
                newActive = Math.min(idx, tabState.count - 1);
            } else {
                newActive = tabState.active;
            }
            
            tabState.active = newActive;
            saveTabState();
            
            // 跳转到新的 active session
            var newSession = tabState.sessions[newActive] || ('tab-' + (newActive + 1));
            window.location.href = '/?session=' + encodeURIComponent(newSession);
        }

        function saveTabState() {
            fetch(TAB_API, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    count: tabState.count,
                    active: tabState.active,
                    names: tabState.names,
                    sessions: tabState.sessions
                })
            }).then(function(r){ return r.json(); }).then(function(s){
                tabState.ts = s.ts;
            });
        }

        function pollTabState() {
            fetch(TAB_API).then(function(r){ return r.json(); }).then(function(s){
                if (s.ts && s.ts !== tabState.ts) {
                    tabState.count = s.count;
                    tabState.active = s.active;
                    tabState.ts = s.ts;
                    if (s.names) tabState.names = s.names;
                    if (s.sessions) tabState.sessions = s.sessions;
                    renderTabs();
                }
            }).catch(function(){});
        }

        setInterval(pollTabState, 600);

        var btnNewTab2 = document.getElementById('btn-newtab2');
        if (btnNewTab2) {
            btnNewTab2.addEventListener('pointerdown', function(e) {
                e.preventDefault();
                var now = Date.now();
                if (now - (window.__btnDebounce['newtab2'] || 0) < 300) return;
                window.__btnDebounce['newtab2'] = now;
                
                // 创建新的 session 名称
                var newSession = 'tab-' + Date.now();
                tabState.names.push(DEFAULT_TAB_NAME);
                tabState.sessions.push(newSession);
                tabState.count++;
                tabState.active = tabState.count - 1;
                saveTabState();
                
                // 跳转到新 session
                window.location.href = '/?session=' + encodeURIComponent(newSession);
            });
        }

        document.addEventListener('keydown', function(e) {
            if (e.altKey && e.key === 'n') {
                var newSession = 'tab-' + Date.now();
                tabState.names.push(DEFAULT_TAB_NAME);
                tabState.sessions.push(newSession);
                tabState.count++;
                tabState.active = tabState.count - 1;
                saveTabState();
                window.location.href = '/?session=' + encodeURIComponent(newSession);
            }
            if (e.altKey && e.key === 'x') {
                if (tabState.count > 1) {
                    closeTab(tabState.active);
                }
            }
            if (e.altKey && e.key === 'ArrowLeft') {
                var newIdx = tabState.active > 0 ? tabState.active - 1 : tabState.count - 1;
                switchToTab(newIdx);
            }
            if (e.altKey && e.key === 'ArrowRight') {
                var newIdx = tabState.active < tabState.count - 1 ? tabState.active + 1 : 0;
                switchToTab(newIdx);
            }
        });

        pollTabState();
        renderTabs();

        // 粘贴功能
        var _pasteCooldown = 0;
        function doPaste() {
            var now = Date.now();
            if (now - _pasteCooldown < 500) return;
            _pasteCooldown = now;
            if (navigator.clipboard && navigator.clipboard.readText) {
                navigator.clipboard.readText().then(function(text) {
                    if (text && term) term.paste(text);
                }).catch(function() {
                    var el = document.getElementById('paste-helper');
                    if (el) { el.value = ''; el.focus(); }
                });
            }
        }

        var btnPaste = document.getElementById('btn-paste');
        if (btnPaste) btnPaste.addEventListener('click', doPaste);

        // 移动端键盘适配
        if (window.visualViewport) {
            var termWrap = document.getElementById('term-wrap');
            var toolbar = document.getElementById('toolbar');
            var tabBar = document.getElementById('tab-bar');
            
            function handleViewportResize() {
                var viewportHeight = window.visualViewport.height;
                var windowHeight = window.innerHeight;
                var keyboardHeight = windowHeight - viewportHeight;
                var isKeyboardVisible = keyboardHeight > 100;
                
                if (termWrap) termWrap.style.height = viewportHeight + 'px';
                if (toolbar) {
                    if (isKeyboardVisible) {
                        toolbar.style.position = 'fixed';
                        toolbar.style.bottom = keyboardHeight + 'px';
                    } else {
                        toolbar.style.position = '';
                        toolbar.style.bottom = '';
                    }
                }
                if (tabBar) {
                    if (isKeyboardVisible) {
                        tabBar.style.position = 'fixed';
                        tabBar.style.bottom = (keyboardHeight + (toolbar ? toolbar.offsetHeight : 162)) + 'px';
                    } else {
                        tabBar.style.position = '';
                        tabBar.style.bottom = '';
                    }
                }
            }
            
            window.visualViewport.addEventListener('resize', handleViewportResize);
            window.visualViewport.addEventListener('scroll', handleViewportResize);
        }
    }
})();
</script>"""

# SSL context
if ZELLIJ == "127.0.0.1" or ZELLIJ == "localhost":
    client_ctx = None
else:
    client_ctx = ssl.create_default_context()
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    client_ctx.set_alpn_protocols(["http/1.1"])


async def handle_auto_login(reader, writer, headers):
    try:
        cl = int(headers.get("content-length", 0))
        body = b""
        if cl > 0:
            body = await asyncio.wait_for(reader.readexactly(cl), timeout=10)

        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        login_body = json.dumps({"auth_token": AUTO_TOKEN, "remember_me": True}).encode()
        req = (
            f"POST /command/login HTTP/1.1\r\n"
            f"Host: {ZELLIJ}:{ZELLIJ_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(login_body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + login_body
        zw.write(req)
        await zw.drain()

        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=10)
        resp_text = resp_head.decode("utf-8", errors="replace")

        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()

        resp_cl = int(rh.get("content-length", 0))
        resp_body = b""
        if resp_cl > 0:
            resp_body = await asyncio.wait_for(zr.readexactly(resp_cl), timeout=10)

        out_headers = []
        for k, v in rh.items():
            out_headers.append(f"{k}: {v}")
        resp_out = resp_text.split("\r\n")[0] + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + resp_body)
        await writer.drain()
        zw.close()
        writer.close()

    except Exception as e:
        msg = f'{{"error": "login: {e}"}}'
        writer.write(
            f"HTTP/1.1 500 Internal Server Error\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(msg)}\r\n"
            f"Connection: close\r\n\r\n{msg}".encode()
        )
        await writer.drain()
        try:
            writer.close()
        except Exception:
            pass


async def handle_auto_session(reader, writer, raw_header):
    try:
        lines = raw_header.split("\r\n")
        headers_dict = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers_dict[k.strip().lower()] = v.strip()
        cl = int(headers_dict.get("content-length", 0))
        if cl > 0:
            await asyncio.wait_for(reader.readexactly(cl), timeout=10)

        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        login_body = json.dumps({"auth_token": AUTO_TOKEN, "remember_me": True}).encode()
        login_req = (
            f"POST /command/login HTTP/1.1\r\n"
            f"Host: {ZELLIJ}:{ZELLIJ_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(login_body)}\r\n"
            f"Connection: keep-alive\r\n"
            f"\r\n"
        ).encode() + login_body
        zw.write(login_req)
        await zw.drain()

        login_resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=10)
        login_resp_text = login_resp_head.decode("utf-8", errors="replace")

        cookie = ""
        for line in login_resp_text.split("\r\n"):
            if line.lower().startswith("set-cookie:"):
                cookie = line.split(":", 1)[1].strip().split(";")[0]

        lrh = {}
        for line in login_resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                lrh[k.strip().lower()] = v.strip()
        lr_cl = int(lrh.get("content-length", 0))
        if lr_cl > 0:
            await asyncio.wait_for(zr.readexactly(lr_cl), timeout=10)

        session_body = json.dumps({"session_name": "default"}).encode()
        session_req = (
            f"POST /session HTTP/1.1\r\n"
            f"Host: {ZELLIJ}:{ZELLIJ_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(session_body)}\r\n"
            f"Cookie: {cookie}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode() + session_body
        zw.write(session_req)
        await zw.drain()

        session_resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=10)
        session_resp_text = session_resp_head.decode("utf-8", errors="replace")

        srh = {}
        for line in session_resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                srh[k.strip().lower()] = v.strip()

        sr_cl = int(srh.get("content-length", 0))
        resp_body = b""
        if sr_cl > 0:
            resp_body = await asyncio.wait_for(zr.readexactly(sr_cl), timeout=10)

        out_headers = []
        for k, v in srh.items():
            out_headers.append(f"{k}: {v}")
        out_headers.append(f"Set-Cookie: {cookie}; HttpOnly; SameSite=Strict; Secure; Path=/; Max-Age=2419200")
        resp_out = session_resp_text.split("\r\n")[0] + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + resp_body)
        await writer.drain()
        zw.close()
        writer.close()

    except Exception as e:
        msg = f'{{"error": "session: {e}"}}'
        writer.write(
            f"HTTP/1.1 500 Internal Server Error\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(msg)}\r\n"
            f"Connection: close\r\n\r\n{msg}".encode()
        )
        await writer.drain()
        try:
            writer.close()
        except Exception:
            pass


async def handle_client(reader, writer):
    try:
        data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
        header_text = data.decode("utf-8", errors="replace")
        lines = header_text.split("\r\n")
        method, path = lines[0].split(" ", 2)[:2]

        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        is_ws = headers.get("upgrade", "").lower() == "websocket"

        if method == "POST" and path == "/command/login":
            await handle_auto_login(reader, writer, headers)
            return

        if method == "POST" and path == "/session":
            await handle_auto_session(reader, writer, header_text)
            return

        if path == "/api/tabs" and method == "GET":
            state = read_tab_state()
            body = json.dumps(state).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            await writer.drain()
            writer.close()
            return

        if path == "/api/tabs" and method == "POST":
            cl = int(headers.get("content-length", 0))
            if cl > 0 and cl < 4096:
                body = await asyncio.wait_for(reader.readexactly(cl), timeout=5)
                try:
                    data = json.loads(body)
                    count = int(data.get("count", 1))
                    active = int(data.get("active", 0))
                    names = data.get("names", None)
                    sessions = data.get("sessions", None)
                    if names is not None and not isinstance(names, list):
                        names = None
                    if sessions is not None and not isinstance(sessions, list):
                        sessions = None
                    state = write_tab_state(count, active, names, sessions)
                    resp = json.dumps(state).encode()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: " + str(len(resp)).encode() + b"\r\n\r\n" + resp)
                except (json.JSONDecodeError, ValueError):
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            else:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        # 删除 session API
        if path.startswith("/api/session/") and method == "DELETE":
            session_name = path[13:]  # 提取 session 名称
            try:
                # 删除 zellij session
                import subprocess
                subprocess.run(
                    [os.path.expanduser("~/.local/bin/zellij"), "delete-session", "-f", session_name],
                    capture_output=True,
                    timeout=5
                )
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
            except Exception as e:
                writer.write(f"HTTP/1.1 500 Internal Server Error\r\nContent-Length: {len(str(e))}\r\n\r\n{str(e)}".encode())
            await writer.drain()
            writer.close()
            return

        if path == "/" and method == "GET" and not is_ws:
            await serve_custom_page(reader, writer, headers, header_text)
            return

        if is_ws:
            await proxy_ws(reader, writer, header_text)
            return

        await proxy_http(reader, writer, headers, header_text)

    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def serve_custom_page(reader, writer, headers, raw_header):
    try:
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        
        # 从 URL 参数获取 session 名称
        lines = raw_header.split("\r\n")
        request_line = lines[0]
        session_name = "default"
        
        # 解析 URL 参数
        if "?" in request_line:
            path_part, query_part = request_line.split("?", 1)
            for param in query_part.split("&"):
                if param.startswith("session="):
                    session_name = param[8:]  # 提取 session 值
                    break
        
        # 构造新的请求行
        lines[0] = f"GET /shared?session={session_name} HTTP/1.1"
        for i, line in enumerate(lines[1:], 1):
            if line.lower().startswith("host:"):
                lines[i] = f"Host: {ZELLIJ}:{ZELLIJ_PORT}"
                break
        new_header = "\r\n".join(lines)
        
        zw.write(new_header.encode())
        await zw.drain()
        
        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=30)
        resp_text = resp_head.decode("utf-8", errors="replace")
        status = resp_text.split("\r\n")[0]
        
        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()
        
        cl = int(rh.get("content-length", 0))
        if cl > 0:
            body_bytes = await asyncio.wait_for(zr.readexactly(cl), timeout=30)
        else:
            body_parts = []
            while True:
                chunk = await asyncio.wait_for(zr.read(65536), timeout=30)
                if not chunk:
                    break
                body_parts.append(chunk)
            body_bytes = b"".join(body_parts)
        
        if b"</head>" in body_bytes:
            body_bytes = body_bytes.replace(b"</head>", INJECT_CSS.encode() + b"\n</head>")
        if b"<body" in body_bytes:
            body_tag = re.search(b'<body[^>]*>', body_bytes)
            if body_tag:
                old_tag = body_tag.group()
                new_tag = old_tag + b"\n<script>window.sessionName = \"default\";</script>\n" + INJECT_WS_INTERCEPT.encode() + b"\n" + INJECT_AUTH.encode()
                body_bytes = body_bytes.replace(old_tag, new_tag, 1)
        if b"</body>" in body_bytes:
            pattern = b'<div id="terminal"[^>]*>'
            replacement = b'<div id="term-wrap"><div id="terminal"'
            match = re.search(pattern, body_bytes)
            if match:
                opening_tag = match.group()
                new_tag = replacement + opening_tag[len(b'<div id="terminal"'):]
                body_bytes = body_bytes.replace(opening_tag, new_tag)
                wrap_script = b"""<script>
var termDiv = document.getElementById('terminal');
if (termDiv && !document.getElementById('term-wrap')) {
    var wrap = document.createElement('div');
    wrap.id = 'term-wrap';
    termDiv.parentNode.insertBefore(wrap, termDiv);
    wrap.appendChild(termDiv);
}
</script>"""
                body_bytes = body_bytes.replace(b"</body>", wrap_script + b"\n</body>")
            body_bytes = body_bytes.replace(b"</body>", INJECT_HTML.encode() + b"\n</body>")
            inject_js = INJECT_JS_TEMPLATE.replace("{username}", CURRENT_USER)
            body_bytes = body_bytes.replace(b"</body>", inject_js.encode() + b"\n</body>")
        
        out_headers = []
        for k, v in rh.items():
            if k == "content-length":
                continue
            if k == "content-security-policy":
                v = "default-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; img-src 'self' data:"
            out_headers.append(f"{k}: {v}")
        out_headers.append(f"content-length: {len(body_bytes)}")
        
        resp_out = status + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + body_bytes)
        await writer.drain()
        zw.close()
        
    except Exception as e:
        import traceback
        print(f"Error in serve_custom_page: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        msg = f"Error: {type(e).__name__}: {e}"
        writer.write(
            f"HTTP/1.1 502 Bad Gateway\r\n"
            f"Content-Length: {len(msg)}\r\n"
            f"Connection: close\r\n\r\n{msg}".encode()
        )
        await writer.drain()
        try:
            writer.close()
        except Exception:
            pass


async def proxy_http(reader, writer, headers, raw_header):
    try:
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        
        lines = raw_header.split("\r\n")
        for i, line in enumerate(lines[1:], 1):
            if line.lower().startswith("host:"):
                lines[i] = f"Host: {ZELLIJ}:{ZELLIJ_PORT}"
                break
        new_header = "\r\n".join(lines)
        
        cl = int(headers.get("content-length", 0))
        body = b""
        if cl > 0:
            body = await asyncio.wait_for(reader.readexactly(cl), timeout=30)
        
        zw.write(new_header.encode() + body)
        await zw.drain()
        
        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=30)
        resp_text = resp_head.decode("utf-8", errors="replace")
        
        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()
        
        resp_cl = int(rh.get("content-length", 0))
        resp_body = b""
        if resp_cl > 0:
            resp_body = await asyncio.wait_for(zr.readexactly(resp_cl), timeout=30)
        else:
            while True:
                chunk = await asyncio.wait_for(zr.read(65536), timeout=5)
                if not chunk:
                    break
                resp_body += chunk
        
        out_headers = []
        for k, v in rh.items():
            if k == "content-security-policy":
                v = "default-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; img-src 'self' data:"
            out_headers.append(f"{k}: {v}")
        
        resp_out = resp_text.split("\r\n")[0] + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + resp_body)
        await writer.drain()
        zw.close()
        writer.close()
        
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def proxy_ws(reader, writer, raw_header):
    try:
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        
        lines = raw_header.split("\r\n")
        for i, line in enumerate(lines[1:], 1):
            if line.lower().startswith("host:"):
                lines[i] = f"Host: {ZELLIJ}:{ZELLIJ_PORT}"
                break
        new_header = "\r\n".join(lines)
        
        zw.write(new_header.encode())
        await zw.drain()
        
        async def forward(src, dst):
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass
        
        await asyncio.gather(
            forward(reader, zw),
            forward(zr, writer)
        )
        
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(CERT, KEY)
    server = await asyncio.start_server(handle_client, "0.0.0.0", LISTEN_PORT, ssl=ssl_ctx)
    print(f"Proxy listening on 0.0.0.0:{LISTEN_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
