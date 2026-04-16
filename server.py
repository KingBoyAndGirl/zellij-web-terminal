#!/usr/bin/env python3
"""Zellij 终端前端 - 提供自定义页面并代理 Zellij 后端"""
import http.server
import urllib.request
import urllib.error
import ssl

ZELLIJ_BACKEND = "https://127.0.0.1:18082"
LISTEN_PORT = 18083
WEB_DIR = "/home/devbox/.config/zellij/web"

# 忽略自签名证书
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class ZellijProxy(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        # 首页
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
            return super().do_GET()
        
        # 其他请求代理到 Zellij
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_GET_HEAD(self):
        self._proxy()

    def _proxy(self):
        url = f"{ZELLIJ_BACKEND}{self.path}"
        try:
            # 读取请求 body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else None

            req = urllib.request.Request(url, data=body, method=self.command)
            
            # 转发 headers
            for key, val in self.headers.items():
                if key.lower() not in ('host', 'connection'):
                    req.add_header(key, val)

            resp = urllib.request.urlopen(req, context=ctx)
            
            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ('transfer-encoding', 'connection'):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, format, *args):
        pass  # 静默日志


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", LISTEN_PORT), ZellijProxy)
    print(f"Zellij 前端运行中: http://127.0.0.1:{LISTEN_PORT}")
    server.serve_forever()
