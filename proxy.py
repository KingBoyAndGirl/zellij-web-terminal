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
AUTO_TOKEN="72213dca-2113-4e81-b68b-0415ea2edd38"
CERT = "/home/devbox/.config/zellij/cert.pem"
KEY = "/home/devbox/.config/zellij/key.pem"
WEB_DIR = "/home/devbox/.config/zellij/web"
TAB_STATE_FILE = os.path.join(WEB_DIR, "tab_state.json")

# ── Tab state management (shared across all devices) ──
import threading

_tab_lock = threading.Lock()

def read_tab_state() -> dict:
    """Read tab state from file. Returns {count, active, names, ts}."""
    try:
        with open(TAB_STATE_FILE, "r") as f:
            state = json.load(f)
        # Ensure names array exists
        if "names" not in state:
            state["names"] = [f"Tab {i+1}" for i in range(state.get("count", 1))]
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"count": 1, "active": 0, "names": ["Tab 1"], "ts": 0}

def write_tab_state(count: int, active: int, names: list = None) -> dict:
    """Write tab state to file and return it."""
    import time
    count = max(1, count)
    active = max(0, min(active, count - 1))
    if names is None:
        # Preserve existing names or generate defaults
        old = read_tab_state()
        old_names = old.get("names", [])
        names = []
        for i in range(count):
            if i < len(old_names):
                names.append(old_names[i])
            else:
                names.append(f"Tab {i+1}")
    else:
        names = names[:count] + [f"Tab {i+1}" for i in range(max(0, count - len(names)))]
    state = {"count": count, "active": active, "names": names, "ts": time.time()}
    with _tab_lock:
        with open(TAB_STATE_FILE, "w") as f:
            json.dump(state, f)
    return state

# Initialize tab state file
if not os.path.exists(TAB_STATE_FILE):
    write_tab_state(1, 0)

# Load custom HTML template (optional, we may not need it)
try:
    with open(os.path.join(WEB_DIR, "index.html"), "r") as f:
        CUSTOM_HTML = f.read()
except:
    CUSTOM_HTML = ""

# CSS to inject
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
    bottom: 128px;
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
.btn:disabled {
    opacity: 0.8; cursor: default; background: #1a1a1a;
    border-color: #555; color: #aaa; font-weight: 600;
    flex: 1.5;  /* wider for "Tab 1/3" text */
}
.panel {
    display: none;
    position: fixed;
    bottom: 86px; left: 0; right: 0;
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
// AND wrap WebSocket.prototype.send for IME dedup (catches ALL send calls)
(function() {
    var OriginalWebSocket = window.WebSocket;
    window._termWs = null;
    window._ctrlWs = null;
    window.__imeComposing = false;
    window.sessionName = window.sessionName || 'default';
    
    // IME dedup state (global, shared by prototype wrapper)
    var _imeLastSent = {d: '', t: 0};
    var _imeIsTerminalWs = function(ws) {
        return ws === window._termWs;
    };
    
    // PROTOTYPE-LEVEL send wrapper: catches ALL send calls regardless of reference
    var _originalProtoSend = WebSocket.prototype.send;
    WebSocket.prototype.send = function(data) {
        if (_imeIsTerminalWs(this)) {
            var _hex = typeof data === 'string' ? Array.from(data).map(function(c){return 'U+'+c.charCodeAt(0).toString(16).padStart(4,'0')}).join(' ') : String(data);
            // Block all sends during IME composition
            if (window.__imeComposing) {
                console.log('[IME] proto.ws.send BLOCK composing:', _hex);
                return;
            }
            // 1000ms identical-text dedup
            var now = Date.now();
            if (typeof data === 'string' && data.length > 0 && data.length < 10000) {
                if (_imeLastSent.d === data && (now - _imeLastSent.t) < 1000) {
                    console.log('[IME] proto.ws.send BLOCK dedup1000:', _hex);
                    return;
                }
                _imeLastSent = {d: data, t: now};
            }
            console.log('[IME] proto.ws.send ACTUAL SEND:', _hex);
        }
        return _originalProtoSend.call(this, data);
    };
    
    // Constructor wrapper for session name rewriting
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
    
    // Helper for buttons to send data (with debounce to prevent double-fire)
    window.__wsSend = function(data) {
        var _d = typeof data === 'string' ? data.substring(0,40) : String(data).substring(0,40);
        if (window.__imeComposing) {
            console.log('[IME] __wsSend BLOCK composing:', _d);
            return true;
        }
        var ws = window._termWs;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(data);
            console.log('[Btn] __wsSend sent:', _d);
            return true;
        }
        return false;
    };
    
    // Button debounce map: prevent same button from firing within 300ms
    window.__btnDebounce = {};
    
    // Server-side PR #5034 fix handles parse_stdin correctly (per-character consumption),
    // so no client-side IME intervention is needed. Let xterm.js handle composition normally.
    var _imeComposing = false;
    document.addEventListener('compositionstart', function() {
        _imeComposing = true;
        console.log('[IME] compositionstart');
    }, true);
    document.addEventListener('compositionend', function(e) {
        _imeComposing = false;
        console.log('[IME] compositionend, data:', e.data);
    }, true);
    
    // Dedup wrapper: prevent ws.send duplicate during compositionend
    // (replaces the older wrapper above - integrated into the same prototype chain)
    ;
    
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
        <button class="btn bl" id="btn-edit">TAB</button>
        <button class="btn rd" id="btn-close">关闭</button>
        <button class="btn" id="btn-hsplit">←分屏</button>
        <button class="btn yl" id="btn-fullscreen">全屏</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-up">↑</button>
        <button class="btn" id="btn-down">↓</button>
        <button class="btn" id="btn-left">←</button>
        <button class="btn" id="btn-right">→</button>
        <button class="btn gn" id="btn-paste">粘贴</button>
        <button class="btn rd" id="btn-ctrlc">^C</button>
    </div>
    <div class="row">
        <button class="btn" id="btn-clear">清屏</button>
        <button class="btn" id="btn-gohome">回家</button>
        <button class="btn" id="btn-history">历史</button>
        <button class="btn gn" id="btn-detach">断开</button>
        <button class="btn rd" id="btn-quit">退出</button>
    </div>
</div>

<div id="tab-bar">
    <div id="tab-list"></div>
    <button class="tab-btn-new" id="btn-newtab2">+</button>
</div>

<div class="panel" id="panel-edit">
    <div class="panel-title">TAB 编辑</div>
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
    <div class="row">
        <button class="btn" id="btn-vsplit">↓分屏</button>
    </div>
</div>

"""

# JavaScript to inject (button bindings and other logic)
INJECT_JS = """<script>
(function() {
    // Wait for terminal to be ready
    var term = null;
    var checkInterval = setInterval(function() {
        if (window.term && window.term._core && window.term._core._compositionHelper) {
            term = window.term;
            clearInterval(checkInterval);
            init();
        }
    }, 100);
    // Fallback: after 5s, init anyway even if CompositionHelper not found
    setTimeout(function() {
        if (!term && window.term) {
            clearInterval(checkInterval);
            term = window.term;
            console.log('[IME] CompositionHelper not found within 5s, init fallback');
            init();
        }
    }, 5000);

    function init() {
        // Server-side PR #5034 fix: parse_stdin now consumes per-character, so no IME duplication.
        // Let xterm.js CompositionHelper work normally - no client-side intervention needed.
        console.log('[IME] Server-side fix active, xterm.js will handle composition normally');

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
            'btn-hsplit': '\\x1bh',
            'btn-vsplit': '\\x1bv',
            'btn-fullscreen': '\\x1bf',
            'btn-detach': '\\x1bd',
            'btn-quit': '\\x1bq',
            'btn-clear': 'clear\\n',
            'btn-gohome': 'cd ~\\n',
            'btn-history': 'history | tail -20\\n'
        };

        // Setup button event listeners
        for (var id in keyMap) {
            var btn = document.getElementById(id);
            if (btn) {
                (function(data, id) {
                    btn.addEventListener('pointerdown', function(e) {
                        e.preventDefault();
                        // 300ms debounce to prevent double-fire
                        var now = Date.now();
                        var last = window.__btnDebounce[id] || 0;
                        if (now - last < 300) {
                            console.log('[Btn] Debounced:', id);
                            return;
                        }
                        window.__btnDebounce[id] = now;
                        if (typeof window.__wsSend === 'function') {
                            window.__wsSend(data);
                        } else {
                            console.error('[Hermes] __wsSend not available');
                        }
                    });
                })(keyMap[id], id);
            }
        }

        // ── Browser-like Tab UI: dynamic tabs with close buttons ──
        var tabState = { count: 1, active: 0, ts: 0, names: [] };
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
                    name.textContent = tabState.names[idx] || ('Tab ' + (idx + 1));

                    var close = document.createElement('button');
                    close.className = 'tab-close';
                    close.textContent = '×';

                    item.appendChild(name);
                    item.appendChild(close);

                    // Click tab to switch
                    item.addEventListener('pointerdown', function(e) {
                        console.log('[Tab Debug] Tab item clicked for idx:', idx, 'target:', e.target.tagName, 'target===close:', e.target === close, 'active:', tabState.active);
                        if (e.target === close) return; // don't switch when clicking close
                        e.preventDefault();
                        var now = Date.now();
                        if (now - (window.__btnDebounce['tabclick'] || 0) < 200) return;
                        window.__btnDebounce['tabclick'] = now;
                        if (idx !== tabState.active) {
                            switchToTab(idx);
                        }
                    });

                    // Click × to close
                    close.addEventListener('pointerdown', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        console.log('[Tab Debug] Close button clicked for idx:', idx, 'active:', tabState.active, 'count:', tabState.count);
                        var now = Date.now();
                        if (now - (window.__btnDebounce['tabclose' + idx] || 0) < 300) return;
                        window.__btnDebounce['tabclose' + idx] = now;
                        closeTab(idx);
                    });

                    tabList.appendChild(item);
                })(i);
            }
            // Scroll active tab into view
            var activeEl = tabList.querySelector('.tab-item.active');
            if (activeEl) activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }

        function switchToTab(idx) {
            var diff = idx - tabState.active;
            if (diff > 0) {
                for (var i = 0; i < diff; i++) window.__wsSend('\x1b[1;3C'); // Alt+Right
            } else if (diff < 0) {
                for (var j = 0; j < -diff; j++) window.__wsSend('\x1b[1;3D'); // Alt+Left
            }
            tabState.active = idx;
            renderTabs();
            saveTabState();
            console.log('[Tab] Switch to:', idx + 1);
        }

        function closeTab(idx) {
            if (tabState.count <= 1) return; // don't close last tab
            // Switch to target tab first if not active
            if (idx !== tabState.active) {
                switchToTab(idx);
            }
            // Send Alt+x to close current tab
            window.__wsSend('\x1bx');
            tabState.names.splice(idx, 1);
            tabState.count--;
            if (tabState.active >= tabState.count) {
                tabState.active = tabState.count - 1;
            }
            renderTabs();
            saveTabState();
            console.log('[Tab] Close:', idx + 1, 'now:', tabState.active + 1 + '/' + tabState.count);
        }

        // Save tab state to server
        function saveTabState() {
            fetch(TAB_API, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({count: tabState.count, active: tabState.active, names: tabState.names})
            }).then(function(r){ return r.json(); }).then(function(s){
                tabState.ts = s.ts;
                console.log('[Tab] Saved:', tabState.active+1 + '/' + tabState.count);
            }).catch(function(e){ console.warn('[Tab] Save failed:', e); });
        }

        // Poll server for tab state changes
        function pollTabState() {
            fetch(TAB_API).then(function(r){ return r.json(); }).then(function(s){
                if (s.ts && s.ts !== tabState.ts) {
                    tabState.count = s.count;
                    tabState.active = s.active;
                    tabState.ts = s.ts;
                    if (s.names) tabState.names = s.names;
                    renderTabs();
                    console.log('[Tab] Synced:', tabState.active+1 + '/' + tabState.count);
                }
            }).catch(function(){});
        }

        setInterval(pollTabState, 600);

        // + button: create new tab
        var btnNewTab2 = document.getElementById('btn-newtab2');
        if (btnNewTab2) {
            btnNewTab2.addEventListener('pointerdown', function(e) {
                e.preventDefault();
                var now = Date.now();
                if (now - (window.__btnDebounce['newtab2'] || 0) < 300) return;
                window.__btnDebounce['newtab2'] = now;
                window.__wsSend('\x1bn');
                // Generate unique name
                var newName = 'Tab ' + (tabState.count + 1);
                var counter = 1;
                while (tabState.names.includes(newName)) {
                    counter++;
                    newName = 'Tab ' + (tabState.count + 1) + ' (' + counter + ')';
                }
                tabState.names.push(newName);
                tabState.count++;
                tabState.active = tabState.count - 1;
                renderTabs();
                saveTabState();
                console.log('[Tab] New:', tabState.active+1 + '/' + tabState.count);
            });
        }

        // Keyboard shortcuts for tab tracking
        document.addEventListener('keydown', function(e) {
            if (e.altKey && e.key === 'n') {
                tabState.names.push('Tab ' + (tabState.count + 1));
                tabState.count++;
                tabState.active = tabState.count - 1;
                renderTabs();
                saveTabState();
            }
            if (e.altKey && e.key === 'x') {
                if (tabState.count > 1) {
                    tabState.names.splice(tabState.active, 1);
                    tabState.count--;
                    if (tabState.active >= tabState.count) tabState.active = tabState.count - 1;
                }
                renderTabs();
                saveTabState();
            }
            if (e.altKey && e.key === 'ArrowLeft') {
                tabState.active = tabState.active > 0 ? tabState.active - 1 : tabState.count - 1;
                renderTabs();
                saveTabState();
            }
            if (e.altKey && e.key === 'ArrowRight') {
                tabState.active = tabState.active < tabState.count - 1 ? tabState.active + 1 : 0;
                renderTabs();
                saveTabState();
            }
        });

        // Initial load
        pollTabState();
        renderTabs();
        

        // Panel toggles
        // Panel toggle - TAB button opens edit panel
        var editPanel = document.getElementById('panel-edit');
        var btnEdit = document.getElementById('btn-edit');
        
        if (btnEdit && editPanel) {
            btnEdit.addEventListener('click', function() {
                editPanel.classList.toggle('open');
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
                el.style.cssText = 'position:fixed;bottom:92px;left:8px;right:8px;z-index:9998;background:#222;border:1px solid #61afef;border-radius:8px;padding:8px;display:flex;gap:6px;align-items:flex-end;';
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
                    termWrap.style.height = (window.visualViewport.height - 123) + 'px';
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

        # Tab state API (shared across all devices)
        if path == "/api/tabs" and method == "GET":
            state = read_tab_state()
            body = json.dumps(state).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            await writer.drain()
            writer.close()
            return

        if path == "/api/tabs" and method == "POST":
            # Read body
            cl = int(headers.get("content-length", 0))
            if cl > 0 and cl < 4096:
                body = await asyncio.wait_for(reader.readexactly(cl), timeout=5)
                try:
                    data = json.loads(body)
                    count = int(data.get("count", 1))
                    active = int(data.get("active", 0))
                    names = data.get("names", None)
                    if names is not None and not isinstance(names, list):
                        names = None
                    state = write_tab_state(count, active, names)
                    resp = json.dumps(state).encode()
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: " + str(len(resp)).encode() + b"\r\n\r\n" + resp)
                except (json.JSONDecodeError, ValueError):
                    writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            else:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
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
        content_length = int(rh.get("content-length", 0))
        if content_length > 0:
            # Read exactly content_length bytes
            remaining = content_length
            while remaining > 0:
                chunk = await asyncio.wait_for(zr.read(min(remaining, 65536)), timeout=15)
                if not chunk:
                    break
                body_parts.append(chunk)
                remaining -= len(chunk)
        else:
            # No content-length: read until timeout (short)
            try:
                while True:
                    chunk = await asyncio.wait_for(zr.read(65536), timeout=2)
                    if not chunk:
                        break
                    body_parts.append(chunk)
            except asyncio.TimeoutError:
                pass
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
        import traceback
        print(f"[PROXY] asset error: {e}", flush=True)
        traceback.print_exc()
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