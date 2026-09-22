# -*- coding: utf-8 -*-
"""
创源印记 · 本地开发服务器（零第三方依赖，Python 3.8+）

功能：
1. 托管 prototype/ 目录的静态前端（访问 http://localhost:8090）
2. /api/generate 代理 DeepSeek 大模型，完成真实 AI 创作
3. /api/hash 由前端直接用 Web Crypto API 计算，无需后端

启动：
    cd server
    # Windows PowerShell
    $env:DEEPSEEK_API_KEY="sk-你的key"
    python app.py
    # Linux / macOS
    DEEPSEEK_API_KEY=sk-xxx python3 app.py

然后浏览器打开 http://localhost:8090
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# ===== 配置 =====
PORT = int(os.environ.get("PORT", "8090"))
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_ENDPOINT = os.environ.get(
    "DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions"
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 前端静态目录（../web —— 与 EdgeOne 线上站点根保持一致，单一前端源）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "web"))

SYSTEM_PROMPT = (
    "你是「创源印记」AI 原生创作确权体系中的创作引擎。用户会给出一个创作意图，"
    "你需要直接产出成品内容，不要解释、不要前后缀寒暄、不要使用 Markdown 代码块。\n"
    "根据创作意图判断体裁：\n"
    "- 若要求诗歌/短诗，输出 4-8 行中文现代诗，意象鲜明；\n"
    "- 若要求海报/视觉/设计方案，输出结构化的视觉方案（主视觉、主标题、副标题、配色、构图要点），每行一条；\n"
    "- 若要求广告/旁白/文案，输出可直接朗读的文案，控制在 80 字以内；\n"
    "- 其他体裁按用户要求产出精炼成品，控制在 200 字以内。\n"
    "只输出作品正文本身。"
)


def call_deepseek(prompt: str) -> dict:
    """调用 DeepSeek，返回 {content, model, usage, raw_prompt}。"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY 环境变量。请先设置后再启动服务器。"
        )
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.9,
        "max_tokens": 600,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + DEEPSEEK_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("DeepSeek API 错误 %s: %s" % (e.code, detail[:500]))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接 DeepSeek：%s" % e.reason)

    content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    content = content.strip().strip("`").strip()
    return {
        "content": content,
        "model": body.get("model", DEEPSEEK_MODEL),
        "usage": body.get("usage", {}),
        "id": body.get("id", ""),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, code: int, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send_json(204, {})

    def do_GET(self):
        """/api/generate 健康探针，与线上 EdgeOne 边缘函数保持同一接口契约。"""
        if self.path.split("?")[0].rstrip("/") != "/api/generate":
            return super().do_GET()
        self._send_json(200, {
            "ok": True,
            "service": "chuangyuan-yinji / api/generate",
            "runtime": "local-python",
            "key_configured": bool(DEEPSEEK_API_KEY),
        })

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") != "/api/generate":
            self._send_json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            params = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            self._send_json(400, {"ok": False, "error": "请求体解析失败: %s" % e})
            return

        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            self._send_json(400, {"ok": False, "error": "缺少 prompt 字段"})
            return
        if len(prompt) > 2000:
            self._send_json(400, {"ok": False, "error": "创作意图过长（>2000字）"})
            return

        t0 = time.time()
        try:
            result = call_deepseek(prompt)
        except Exception as e:
            self._send_json(502, {"ok": False, "error": str(e)})
            return

        result["ok"] = True
        result["latency_ms"] = int((time.time() - t0) * 1000)
        result["server_time"] = int(time.time())
        self._send_json(200, result)


def main():
    if not DEEPSEEK_API_KEY:
        print("=" * 64)
        print("提示：尚未设置 DEEPSEEK_API_KEY 环境变量。")
        print("  PowerShell : $env:DEEPSEEK_API_KEY='sk-xxxx'; python app.py")
        print("  Bash       : DEEPSEEK_API_KEY=sk-xxxx python3 app.py")
        print("未设置时前端可打开，但「真实AI生成」将不可用（自动降级为本地演示）。")
        print("=" * 64)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("创源印记本地服务已启动：")
    print("  前端体验：http://localhost:%d" % PORT)
    print("  AI 接口 ：POST http://localhost:%d/api/generate" % PORT)
    print("  静态目录：%s" % STATIC_DIR)
    print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
