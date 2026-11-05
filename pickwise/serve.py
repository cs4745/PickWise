"""本地更新服务：为报告右上角「更新数据」按钮提供后端。

只监听 127.0.0.1，不对外暴露；零第三方依赖。
GET  /                -> 报告页面
POST /api/update      -> 增量采集 + 重新分析 + 重新生成报告，返回最新数据
GET  /api/status      -> 当前数据生成时间
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import GAME_ORDER, OUTPUT_DIR

_UPDATE_LOCK = threading.Lock()
_DEFAULTS = {"rec_count": 3, "rounds": 200, "window": 250, "seed": 20261105}


def run_update(options=None):
    """增量采集并重建报告，返回 (data, message)；并发时返回 (None, 提示)。"""
    from .fetch import fetch_all
    from .report import build_data, generate

    opts = {**_DEFAULTS, **(options or {})}
    if not _UPDATE_LOCK.acquire(blocking=False):
        return None, "已有更新任务正在进行中，请稍后再试"
    try:
        info = fetch_all(list(GAME_ORDER), full=False, verbose=False)
        added = sum(v.get("new_rows", 0) for v in info["games"].values())
        data = build_data(**opts)
        generate(data)
        latest = ", ".join(
            f"{v['name']} 第 {v['latest']['issue']} 期"
            for v in (data["games"][k]["analysis"] for k in GAME_ORDER)
        )
        return data, f"新增 {added} 期；{latest}"
    finally:
        _UPDATE_LOCK.release()


class _Handler(BaseHTTPRequestHandler):
    server_version = "PickWise/1.0"

    def log_message(self, fmt, *args):
        # 保持控制台安静，只在更新接口打印
        if "POST /api/update" in (self.path or ""):
            print("  [更新数据] " + (fmt % args))

    def _send(self, code, body: bytes, ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/report.html"):
            p = OUTPUT_DIR / "report.html"
            if p.exists():
                self._send(200, p.read_bytes(), "text/html; charset=utf-8")
            else:
                self._json(404, {"ok": False, "error": "尚未生成报告，请先运行 python pickwise.py report"})
        elif path in ("/api/status", "/api/data"):
            p = OUTPUT_DIR / "analysis.json"
            if not p.exists():
                self._json(404, {"ok": False, "error": "尚无分析数据"})
                return
            if path == "/api/status":
                meta = json.loads(p.read_text(encoding="utf-8")).get("meta", {})
                self._json(200, {"ok": True, **meta})
            else:
                self._send(200, p.read_bytes(), "application/json; charset=utf-8")
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/update":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            data, message = run_update()
            if data is None:
                self._json(409, {"ok": False, "error": message})
            else:
                self._json(200, {"ok": True, "message": message, "data": data})
        except Exception as exc:  # noqa: BLE001 - 把错误原样返回给页面显示
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host="127.0.0.1", port=8765, options=None):
    """启动本地服务（阻塞，Ctrl+C 结束）。"""
    globals()["_DEFAULTS"] = {**_DEFAULTS, **(options or {})}
    srv = _Server((host, port), _Handler)
    print(f"买什么 PickWise 本地服务已启动： http://{host}:{port}/")
    print("点击报告右上角「更新数据」即可增量采集并重算；Ctrl+C 停止服务。")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        srv.server_close()
