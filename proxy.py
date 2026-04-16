#!/usr/bin/env python3
"""Zellij Gateway - TLS on 18082, proxy to Zellij on 18084"""
import asyncio
import ssl
import os
import json
import logging
import re
from typing import Optional, Dict, Tuple

ZELLIJ = "127.0.0.1"
ZELLIJ_PORT = 18084
LISTEN_PORT = 18082
# Auto-login token (created via: zellij web --create-token)
AUTO_TOKEN = "f48eed44-0fbe-4eba-a966-5ccaee873bc9"
CERT = "/home/devbox/.config/zellij/cert.pem"
KEY = "/home/devbox/.config/zellij/key.pem"
WEB_DIR = "/home/devbox/.config/zellij/web"

# Load custom HTML template (optional, we may not need it)
try:
    with open(os.path.join(WEB_DIR, "index.html"), "r") as f:
        CUSTOM_HTML = f.read()
except:
    CUSTOM_HTML = ""

# CSS to inject
INJECT_CSS = """<style>
#term-wrap {
    position: absolute;
    top: 0; left: 0; right: 0;
    bottom: 90px;
    background: #000;
}
#terminal {
    width: 100%;
    height: 100%;
}
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
.btn.pk { background: #3a1a3a; border-color: #c678dd; color: #c678dd; }
.panel {
    display: none;
    position: fixed;
    bottom: 90px; left: 0; right: 0;
    background: #111; border-top: 1px solid #333;
    padding: 8px; z-index: 998;
    max-height: 50vh; overflow-y: auto;
}
.panel.open { display: block; }
.panel-title { color: #666; font-size: 11px; margin-bottom: 4px; padding-left: 2px; }
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

# WebSocket interception script - must run before any module scripts
INJECT_WS_INTERCEPT = """<script>
// Intercept WebSocket to force session name for multi-device sharing
// This runs early, before Zellij's module scripts execute
(function() {
    var OriginalWebSocket = window.WebSocket;
    window._termWs = null;  // Terminal WebSocket
    window._ctrlWs = null;  // Control WebSocket
    // IME composition guard (fix Win11 Chinese input doubling)
    window.__imeComposing = false;
    // Default session name, can be overridden by injected script
    window.sessionName = window.sessionName || 'default';
    
    window.WebSocket = function(url, protocols) {
        // Modify URL to use the configured session name
        if (url.indexOf('/ws/terminal') > -1) {
            var parsed = new URL(url, window.location.origin);
            var path = parsed.pathname;
            // If path is exactly /ws/terminal or /ws/terminal/ (no session name)
            if (path === '/ws/terminal' || path === '/ws/terminal/') {
                parsed.pathname = '/ws/terminal/' + window.sessionName;
                url = parsed.toString();
            }
        }
        
        var ws = protocols ? new OriginalWebSocket(url, protocols) : new OriginalWebSocket(url);
        
        // Store reference based on URL
        if (url.indexOf('/ws/terminal') > -1) {
            window._termWs = ws;
            // Wrap ws.send with dedup to prevent double paste from
            // ClipboardAddon + any residual handlers (buttons, etc.)
            var _nativeSend = ws.send.bind(ws);
            window.__imeNativeSend = _nativeSend;
            var _lastSent = {d: '', t: 0};
            ws.send = function(data) {
                // Block all sends during IME composition
                if (window.__imeComposing) {
                    return;
                }
                var now = Date.now();
                if (typeof data === 'string' && data.length > 0 && data.length < 10000) {
                    if (_lastSent.d === data && (now - _lastSent.t) < 200) {
                        return;
                    }
                    _lastSent = {d: data, t: now};
                }
                _nativeSend(data);
            };
        } else if (url.indexOf('/ws/control') > -1) {
            window._ctrlWs = ws;
        }
        
        return ws;
    };
    
    // Copy static properties
    window.WebSocket.CONNECTING = OriginalWebSocket.CONNECTING;
    window.WebSocket.OPEN = OriginalWebSocket.OPEN;
    window.WebSocket.CLOSING = OriginalWebSocket.CLOSING;
    window.WebSocket.CLOSED = OriginalWebSocket.CLOSED;
    
    // Helper function to send data to terminal WebSocket
    // Dedup state for __wsSend
    window.__wsLast = {d: '', t: 0};
    window.__wsSend = function(data) {
        // Block during IME composition
        if (window.__imeComposing) {
            return true;
        }
        var ws = window._termWs;
        if (ws && ws.readyState === WebSocket.OPEN) {
            // Deduplicate: drop exact same data within 200ms
            var now = Date.now();
            if (typeof data === 'string' && data.length > 0 && data.length < 10000) {
                if (window.__wsLast.d === data && (now - window.__wsLast.t) < 200) {
                    return true;
                }
                window.__wsLast = {d: data, t: now};
            }
            ws.send(data);
            return true;
        }
        return false;
    };
    
    // IME Composition event handlers (capture-phase, fires before xterm.js)
    document.addEventListener('compositionstart', function() {
        window.__imeComposing = true;
    }, true);
    document.addEventListener('compositionupdate', function() {
        // intermediate state — ws.send is already blocked
    }, true);
    document.addEventListener('compositionend', function(e) {
        // Keep flag TRUE — do NOT clear here
        var finalText = e.data || '';
        if (finalText.length > 0 && window.__imeNativeSend) {
            window.__imeNativeSend(finalText);
        }
        // Clear flag after 100ms — catches xterm.js deferred handlers
        setTimeout(function() {
            window.__imeComposing = false;
        }, 100);
    }, true);
    // Block keyboard events during composition (stops xterm.js keydown handler)
    document.addEventListener('keydown', function(e) {
        if (window.__imeComposing) {
            e.stopImmediatePropagation();
            e.preventDefault();
        }
    }, true);
    
})();
</script>"""

# Auto-login script - runs before module scripts, auto-authenticates with token
INJECT_AUTH = """<script>
// Auto-login: call /command/login before auth.js runs
(function() {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/command/login', false); // synchronous for reliability
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.send(JSON.stringify({auth_token: '', remember_me: true}));
    if (xhr.status === 200) {
        document.body.dataset.authenticated = 'true';
    }
})();
</script>"""

# HTML for toolbar and panels
INJECT_HTML = """<div id="toolbar">
    <div class="row">
        <button class="btn" id="btn-esc">ESC</button>
        <button class="btn" id="btn-enter">↵ Enter</button>
        <button class="btn" id="btn-newline">↩ 换行</button>
        <button class="btn bl" id="btn-edit">编辑</button>
        <button class="btn pk" id="btn-zellij">操作</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-up">↑</button>
        <button class="btn" id="btn-down">↓</button>
        <button class="btn" id="btn-left">←</button>
        <button class="btn" id="btn-right">→</button>
        <button class="btn gn" id="btn-paste">粘贴</button>
        <button class="btn rd" id="btn-ctrlc">^C</button>
    </div>
</div>

<div class="panel" id="panel-edit">
    <div class="panel-title">编辑</div>
    <div class="row">
        <button class="btn" id="btn-tab">TAB</button>
        <button class="btn" id="btn-backspace">⌫</button>
        <button class="btn" id="btn-delete">⌦</button>
        <button class="btn" id="btn-home">↖</button>
        <button class="btn" id="btn-end">↘</button>
    </div>
    <div class="row">
        <button class="btn bl" id="btn-copy">📋 复制</button>
        <button class="btn bl" id="btn-paste2">📌 粘贴</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-ctrla">^A 行首</button>
        <button class="btn" id="btn-ctrle">^E 行尾</button>
        <button class="btn" id="btn-ctrlu">^U 删行</button>
        <button class="btn" id="btn-ctrlk">^K 删尾</button>
        <button class="btn" id="btn-ctrlw">^W 删词</button>
    </div>
    <div class="row">
        <button class="btn gn" id="btn-save">💾 :wq!</button>
        <button class="btn rd" id="btn-quitvim">❌ :q!</button>
        <button class="btn yl" id="btn-search">🔍 搜索</button>
        <button class="btn" id="btn-search-prev">◀ 上一个</button>
        <button class="btn" id="btn-search-next">▶ 下一个</button>
    </div>
</div>

<div class="panel" id="panel-zellij">
    <div class="panel-title">Zellij 操作</div>
    <div class="row">
        <button class="btn bl" id="btn-newtab">新Tab</button>
        <button class="btn rd" id="btn-close">关闭</button>
        <button class="btn" id="btn-hsplit">←分屏</button>
        <button class="btn" id="btn-vsplit">↓分屏</button>
        <button class="btn yl" id="btn-fullscreen">全屏</button>
    </div>
    <div class="row">
        <button class="btn gn" id="btn-detach">断开</button>
        <button class="btn rd" id="btn-quit">退出</button>
    </div>
    <div class="panel-title">Tab 切换</div>
    <div class="row">
        <button class="btn" id="btn-tab1">Tab1</button>
        <button class="btn" id="btn-tab2">Tab2</button>
        <button class="btn" id="btn-tab3">Tab3</button>
        <button class="btn" id="btn-tab4">Tab4</button>
        <button class="btn" id="btn-tab5">Tab5</button>
    </div>
    <div class="panel-title">工具</div>
    <div class="row">
        <button class="btn" id="btn-clear">清屏</button>
        <button class="btn" id="btn-home">回家</button>
        <button class="btn" id="btn-history">历史</button>
    </div>
</div>

"""

# JavaScript to inject (button bindings and other logic)
INJECT_JS = """<script>
(function() {
    // Wait for terminal to be ready
    var term = null;
    var checkInterval = setInterval(function() {
        if (window.term) {
            term = window.term;
            clearInterval(checkInterval);
            init();
        }
    }, 100);

    function init() {
        // Button mappings - ESC sequences
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
            'btn-home': '\\x1b[H',
            'btn-end': '\\x1b[F',
            'btn-ctrla': '\\x01',
            'btn-ctrle': '\\x05',
            'btn-ctrlu': '\\x15',
            'btn-ctrlk': '\\x0b',
            'btn-ctrlw': '\\x17',
            // vim & search
            'btn-search': String.fromCharCode(12),  // Ctrl+R reverse search
            'btn-search-prev': String.fromCharCode(12),  // Ctrl+R = previous match
            'btn-search-next': String.fromCharCode(19),  // Ctrl+S = next match
            'btn-save': '\\x1b:wq!\\r',    // ESC + :wq!
            'btn-quitvim': '\\x1b:q!\\r',    // ESC + :q!
            'btn-ctrlc': '\\x03',
            'btn-newtab': '\\x1bn',
            'btn-close': '\\x1bx',
            'btn-hsplit': '\\x1bh',
            'btn-vsplit': '\\x1bv',
            'btn-fullscreen': '\\x1bf',
            'btn-detach': '\\x1bd',
            'btn-quit': '\\x1bq',
            'btn-tab1': '\\x1b1',
            'btn-tab2': '\\x1b2',
            'btn-tab3': '\\x1b3',
            'btn-tab4': '\\x1b4',
            'btn-tab5': '\\x1b5',
            'btn-clear': 'clear\\n',
            'btn-history': 'history | tail -20\\n'
        };

        // Setup button event listeners
        for (var id in keyMap) {
            var btn = document.getElementById(id);
            if (btn) {
                (function(data) {
                    btn.addEventListener('pointerdown', function(e) {
                        e.preventDefault();
                        if (typeof window.__wsSend === 'function') {
                            window.__wsSend(data);
                        } else {
                            console.error('[Hermes] __wsSend not available');
                        }
                    });
                })(keyMap[id]);
            }
        }

        // Panel toggles
        var editPanel = document.getElementById('panel-edit');
        var zellijPanel = document.getElementById('panel-zellij');
        var btnEdit = document.getElementById('btn-edit');
        var btnZellij = document.getElementById('btn-zellij');
        
        if (btnEdit && editPanel) {
            btnEdit.addEventListener('click', function() {
                editPanel.classList.toggle('open');
                if (editPanel.classList.contains('open') && zellijPanel) {
                    zellijPanel.classList.remove('open');
                }
            });
        }
        if (btnZellij && zellijPanel) {
            btnZellij.addEventListener('click', function() {
                zellijPanel.classList.toggle('open');
                if (zellijPanel.classList.contains('open') && editPanel) {
                    editPanel.classList.remove('open');
                }
            });
        }

        // Copy function - use execCommand for broader compatibility
        var btnCopy = document.getElementById('btn-copy');
        if (btnCopy) {
            btnCopy.addEventListener('click', function() {
                if (term && term.hasSelection && term.hasSelection()) {
                    var text = term.getSelection();
                    var ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.position = 'fixed';
                    ta.style.left = '-9999px';
                    document.body.appendChild(ta);
                    ta.select();
                    try {
                        document.execCommand('copy');
                        flash('已复制 ✓');
                    } catch(e) {
                        flash('复制失败');
                    }
                    document.body.removeChild(ta);
                } else {
                    flash('请先选中文本');
                }
            });
        }

        // Paste helper for iOS (no permission required)
        // Paste function — clipboard.readText + 500ms cooldown + in-callback dedup
        var _pasteCooldown = 0;
        var _lastPastedText = '';
        function doPaste() {
            var now = Date.now();
            if (now - _pasteCooldown < 500) {
                return;
            }
            _pasteCooldown = now;
            _lastPastedText = '';
            if (navigator.clipboard && navigator.clipboard.readText) {
                navigator.clipboard.readText().then(function(text) {
                    if (text && text !== _lastPastedText) {
                        _lastPastedText = text;
                        term.paste(text);
                        flash('已粘贴');
                    }
                }).catch(function(err) {
                    showPasteArea();
                });
            } else {
                showPasteArea();
            }
        }
        
        // iOS fallback: visible textarea for manual paste
        function showPasteArea() {
            var el = document.getElementById('paste-area');
            if (!el) {
                el = document.createElement('div');
                el.id = 'paste-area';
                el.style.cssText = 'position:fixed;bottom:96px;left:8px;right:8px;z-index:9998;background:#222;border:1px solid #61afef;border-radius:8px;padding:8px;display:flex;gap:6px;align-items:flex-end;';
                var ta = document.createElement('textarea');
                ta.id = 'paste-area-input';
                ta.style.cssText = 'flex:1;height:60px;background:#111;color:#ddd;border:1px solid #444;border-radius:5px;padding:6px;font-family:monospace;font-size:13px;resize:none;outline:none;';
                ta.placeholder = '长按粘贴文本...';
                var sendBtn = document.createElement('button');
                sendBtn.textContent = '发送';
                sendBtn.style.cssText = 'background:#98c379;color:#111;border:none;border-radius:5px;padding:10px 14px;font-size:13px;font-weight:600;cursor:pointer;height:fit-content;';
                sendBtn.onclick = function() {
                    if (ta.value) {
                        term.paste(ta.value);
                        flash('已粘贴');
                    }
                    el.style.display = 'none';
                    ta.value = '';
                };
                var closeBtn = document.createElement('button');
                closeBtn.textContent = 'X';
                closeBtn.style.cssText = 'background:#555;color:#ddd;border:none;border-radius:5px;padding:10px 10px;font-size:13px;cursor:pointer;height:fit-content;';
                closeBtn.onclick = function() { el.style.display = 'none'; ta.value = ''; };
                el.appendChild(ta);
                el.appendChild(sendBtn);
                el.appendChild(closeBtn);
                document.body.appendChild(el);
            }
            el.style.display = 'flex';
            setTimeout(function() { document.getElementById('paste-area-input').focus(); }, 100);
        }

        var triggerPaste = doPaste;
        // Bind paste buttons
        var btnPaste = document.getElementById('btn-paste');
        var btnPaste2 = document.getElementById('btn-paste2');
        if (btnPaste) btnPaste.addEventListener('click', doPaste);
        if (btnPaste2) btnPaste2.addEventListener('click', doPaste);

        // Flash notification
        function flash(msg) {
            var el = document.createElement('div');
            el.textContent = msg;
            el.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#333;color:#fff;padding:12px 24px;border-radius:8px;font-size:16px;z-index:9999;pointer-events:none;';
            document.body.appendChild(el);
            setTimeout(function() { el.remove(); }, 1000);
        }

        // Zellij uses ClipboardAddon (@xterm/addon-clipboard) natively for paste.
        // input.js passes Cmd+V/Ctrl+Shift+V through to xterm.js, which handles
        // clipboard read → onData → sendFunction → ws.send.
        // We do NOT intercept paste events — let xterm.js handle everything.
        // For Chinese IME, xterm.js natively handles composition events.
        // For button paste: use term.paste(text) instead of __wsSend to go through
        // the same xterm.js input pipeline as Ctrl+Shift+V (proven no duplication).
        // Keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && (e.shiftKey || e.altKey)) {
                e.preventDefault();
                if (typeof window.__wsSend === 'function') {
                    window.__wsSend('\\n');
                }
                return;
            }
            if (e.key === 'C' && e.ctrlKey && e.shiftKey) {
                e.preventDefault();
                // Copy selection
                if (term && term.hasSelection && term.hasSelection()) {
                    var selection = term.getSelection();
                    navigator.clipboard.writeText(selection).then(function() {
                        flash('已复制 ✓');
                    }).catch(function() {
                        flash('复制失败');
                    });
                }
                return;
            }
            // Cmd+V / Ctrl+V / Ctrl+Shift+V — let xterm.js + ClipboardAddon handle natively.
            // Zellij's input.js passes these through to xterm.js.
        });

        // Visual viewport resize
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', function() {
                var termWrap = document.getElementById('term-wrap');
                if (termWrap) {
                    termWrap.style.height = (window.visualViewport.height - 90) + 'px';
                }
            });
        }
    }
})();
</script>"""

client_ctx = ssl.create_default_context()
client_ctx.check_hostname = False
client_ctx.verify_mode = ssl.CERT_NONE
client_ctx.set_alpn_protocols(["http/1.1"])


async def handle_auto_login(reader, writer, headers):
    """Intercept /command/login, forward to Zellij with auto-token."""
    try:
        # Read the request body (may contain remember_me)
        cl = int(headers.get("content-length", 0))
        body = b""
        if cl > 0:
            body = await asyncio.wait_for(reader.readexactly(cl), timeout=10)

        # Forward to Zellij with our auto-token
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

        # Read response
        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=10)
        resp_text = resp_head.decode("utf-8", errors="replace")

        # Parse response headers for Set-Cookie
        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()

        # Read body
        resp_cl = int(rh.get("content-length", 0))
        resp_body = b""
        if resp_cl > 0:
            resp_body = await asyncio.wait_for(zr.readexactly(resp_cl), timeout=10)
        else:
            while True:
                chunk = await asyncio.wait_for(zr.read(4096), timeout=5)
                if not chunk:
                    break
                resp_body += chunk

        # Forward response to client
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
    """Handle /session by directly calling Zellij with our auto-token cookie."""
    try:
        # Read the original request body (needed to drain it)
        lines = raw_header.split("\r\n")
        headers_dict = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers_dict[k.strip().lower()] = v.strip()
        cl = int(headers_dict.get("content-length", 0))
        if cl > 0:
            await asyncio.wait_for(reader.readexactly(cl), timeout=10)

        # First, login to get a valid cookie
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

        # Read login response to get cookie
        login_resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=10)
        login_resp_text = login_resp_head.decode("utf-8", errors="replace")

        # Parse Set-Cookie
        cookie = ""
        for line in login_resp_text.split("\r\n"):
            if line.lower().startswith("set-cookie:"):
                cookie = line.split(":", 1)[1].strip().split(";")[0]

        # Drain login response body
        lrh = {}
        for line in login_resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                lrh[k.strip().lower()] = v.strip()
        lr_cl = int(lrh.get("content-length", 0))
        if lr_cl > 0:
            await asyncio.wait_for(zr.readexactly(lr_cl), timeout=10)

        # Now call /session with the cookie
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

        # Read session response
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
        else:
            while True:
                chunk = await asyncio.wait_for(zr.read(4096), timeout=5)
                if not chunk:
                    break
                resp_body += chunk

        # Forward session response to client with our Set-Cookie from login
        out_headers = []
        for k, v in srh.items():
            out_headers.append(f"{k}: {v}")
        # Add the login cookie so the browser stores it
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

        # Auto-auth: intercept login and session endpoints
        if method == "POST" and path == "/command/login":
            await handle_auto_login(reader, writer, headers)
            return

        if method == "POST" and path == "/session":
            await handle_auto_session(reader, writer, header_text)
            return

        if path == "/" and method == "GET" and not is_ws:
            # Serve custom page: fetch Zellij's /shared and inject our UI
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
    """Fetch Zellij's /shared page and inject our UI"""
    try:
        # Connect to Zellij
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        
        # Request /shared?session=default (fixed session name for multi-device sharing)
        lines = raw_header.split("\r\n")
        lines[0] = "GET /shared?session=default HTTP/1.1"
        # Ensure Host header points to Zellij
        for i, line in enumerate(lines[1:], 1):
            if line.lower().startswith("host:"):
                lines[i] = f"Host: {ZELLIJ}:{ZELLIJ_PORT}"
                break
        new_header = "\r\n".join(lines)
        
        zw.write(new_header.encode())
        await zw.drain()
        
        # Read response
        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=30)
        resp_text = resp_head.decode("utf-8", errors="replace")
        status = resp_text.split("\r\n")[0]
        
        # Parse response headers
        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()
        
        # Read body
        cl = int(rh.get("content-length", 0))
        if cl > 0:
            body_bytes = await asyncio.wait_for(zr.readexactly(cl), timeout=30)
        else:
            # Read until connection closes
            body_parts = []
            while True:
                chunk = await asyncio.wait_for(zr.read(65536), timeout=30)
                if not chunk:
                    break
                body_parts.append(chunk)
            body_bytes = b"".join(body_parts)
        
        # Modify HTML: inject our CSS, HTML, and JS
        if b"</head>" in body_bytes:
            # Inject session name setting before WebSocket interceptor
            session_script = b'<script>window.sessionName = "default";</script>'
            body_bytes = body_bytes.replace(b"</head>", INJECT_CSS.encode() + b"\n</head>")
        if b"<body" in body_bytes:
            # Inject auto-login script right after <body> tag, before module scripts
            body_bytes = body_bytes.replace(
                b"<body",
                b"<body",
                1
            )
            # Find <body...> and inject after it
            import re
            body_tag = re.search(b'<body[^>]*>', body_bytes)
            if body_tag:
                old_tag = body_tag.group()
                new_tag = old_tag + b"\n<script>window.sessionName = \"default\";</script>\n" + INJECT_WS_INTERCEPT.encode() + b"\n" + INJECT_AUTH.encode()
                body_bytes = body_bytes.replace(old_tag, new_tag, 1)
        if b"</body>" in body_bytes:
            # First, wrap terminal div in term-wrap if not already wrapped
            # Use regex-like replace: <div id="terminal" ...> -> <div id="term-wrap"><div id="terminal" ...>
            import re
            # Pattern to match <div id="terminal" followed by any attributes
            pattern = b'<div id="terminal"[^>]*>'
            replacement = b'<div id="term-wrap"><div id="terminal"'
            # We need to preserve the original attributes
            # Find the opening tag and replace it
            match = re.search(pattern, body_bytes)
            if match:
                # Get the full opening tag
                opening_tag = match.group()
                # Replace with wrapped version, preserving original tag
                new_tag = replacement + opening_tag[len(b'<div id="terminal"'):]
                body_bytes = body_bytes.replace(opening_tag, new_tag)
                # Now we need to close term-wrap before </body>. We'll add a script to do it dynamically.
                # Actually, we can just add a closing div after terminal, but we don't know where terminal ends.
                # Let's use JavaScript to wrap it if not already wrapped.
                wrap_script = b"""<script>
// Wrap terminal in term-wrap if not already wrapped
var termDiv = document.getElementById('terminal');
if (termDiv && !document.getElementById('term-wrap')) {
    var wrap = document.createElement('div');
    wrap.id = 'term-wrap';
    termDiv.parentNode.insertBefore(wrap, termDiv);
    wrap.appendChild(termDiv);
}
</script>"""
                body_bytes = body_bytes.replace(b"</body>", wrap_script + b"\n</body>")
            # Now inject HTML and JS before </body>
            body_bytes = body_bytes.replace(b"</body>", INJECT_HTML.encode() + b"\n</body>")
            body_bytes = body_bytes.replace(b"</body>", INJECT_JS.encode() + b"\n</body>")
        
        # Build response
        out_headers = []
        for k, v in rh.items():
            if k == "content-length":
                continue
            if k == "content-security-policy":
                # Allow inline scripts (our injected UI) and unsafe-eval
                v = "default-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws: wss:; img-src 'self' data:"
            out_headers.append(f"{k}: {v}")
        out_headers.append(f"content-length: {len(body_bytes)}")
        
        resp_out = status + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + body_bytes)
        await writer.drain()
        zw.close()
        
    except Exception as e:
        import traceback, sys
        print(f"Error in serve_custom_page: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        msg = f"Error: {type(e).__name__}: {e}"
        writer.write(
            f"HTTP/1.1 502 Bad Gateway\r\n"
            f"Content-Length: {len(msg)}\r\n"
            f"Connection: close\r\n\r\n{msg}".encode()
        )
        await writer.drain()
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def proxy_ws(reader, writer, raw_header):
    try:
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        zw.write(raw_header.encode())
        await zw.drain()
        await asyncio.gather(pipe(reader, zw), pipe(zr, writer))
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def proxy_http(reader, writer, headers, raw_header):
    try:
        zr, zw = await asyncio.open_connection(ZELLIJ, ZELLIJ_PORT, ssl=client_ctx)
        zw.write(raw_header.encode())
        await zw.drain()

        cl = int(headers.get("content-length", 0))
        if cl > 0:
            body = await asyncio.wait_for(reader.readexactly(cl), timeout=30)
            zw.write(body)
            await zw.drain()

        resp_head = await asyncio.wait_for(zr.readuntil(b"\r\n\r\n"), timeout=30)
        resp_text = resp_head.decode("utf-8", errors="replace")
        status = resp_text.split("\r\n")[0]

        rh = {}
        for line in resp_text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                rh[k.strip().lower()] = v.strip()

        body_parts = []
        while True:
            chunk = await asyncio.wait_for(zr.read(65536), timeout=30)
            if not chunk:
                break
            body_parts.append(chunk)
        body_bytes = b"".join(body_parts)
        # Inject fix for HTML pages
        is_html = "text/html" in rh.get("content-type", "")
        if is_html:
            if b"</head>" in body_bytes:
                body_bytes = body_bytes.replace(b"</head>", INJECT_CSS.encode() + b"\n</head>")
            if b"</body>" in body_bytes:
                body_bytes = body_bytes.replace(b"</body>", INJECT_JS.encode() + b"\n</body>")

        out_headers = []
        for k, v in rh.items():
            if k == "x-frame-options":
                continue
            if k == "content-security-policy":
                # Allow inline scripts (our injected UI) and unsafe-eval
                v = "default-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' ws: wss:; img-src 'self' data:"
            if k == "content-length":
                continue
            out_headers.append(f"{k}: {v}")
        out_headers.append(f"content-length: {len(body_bytes)}")

        resp_out = status + "\r\n" + "\r\n".join(out_headers) + "\r\n\r\n"
        writer.write(resp_out.encode() + body_bytes)
        await writer.drain()
        zw.close()

    except Exception as e:
        msg = f"Error: {e}"
        writer.write(
            f"HTTP/1.1 502 Bad Gateway\r\n"
            f"Content-Length: {len(msg)}\r\n"
            f"Connection: close\r\n\r\n{msg}".encode()
        )
        await writer.drain()
    finally:
        try:
            writer.close()
        except Exception:
            pass

async def pipe(src, dst):
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass

async def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    server = await asyncio.start_server(
        handle_client, "0.0.0.0", LISTEN_PORT, ssl=ctx
    )
    print(f"Gateway running on https://0.0.0.0:{LISTEN_PORT}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())