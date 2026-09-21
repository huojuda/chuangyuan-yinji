# -*- coding: utf-8 -*-
"""
创源印记 · Vercel Serverless Function —— 真实 AI 创作接口
路由：POST /api/generate

线上部署：
1. 将本仓库导入 Vercel（New Project → Import Git Repository）
2. 在 Vercel 项目 Settings → Environment Variables 添加：
       DEEPSEEK_API_KEY = sk-xxxx
   （可选）DEEPSEEK_MODEL = deepseek-chat
3. 部署后前端通过同源 /api/generate 调用，无需暴露密钥。

请求体：{"prompt": "创作意图", "creator": "可选"}
返回：  {"ok": true, "content": "...", "model": "...", "usage": {...}}
"""
import json
import os
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

DEEPSEEK_ENDPOINT = os.environ.get(
    "DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions"
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

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


def _json_response(handler, code, obj):
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(raw)


def _call_deepseek(prompt):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("服务端未配置 DEEPSEEK_API_KEY 环境变量")
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
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("DeepSeek API 错误 %s: %s" % (e.code, detail[:400]))
    content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    return {
        "content": content.strip().strip("`").strip(),
        "model": body.get("model", DEEPSEEK_MODEL),
        "usage": body.get("usage", {}),
        "id": body.get("id", ""),
    }


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_OPTIONS(self):
        self._cors()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            params = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            return _json_response(self, 400, {"ok": False, "error": "请求体解析失败: %s" % e})

        prompt = (params.get("prompt") or "").strip()
        if not prompt:
            return _json_response(self, 400, {"ok": False, "error": "缺少 prompt 字段"})
        if len(prompt) > 2000:
            return _json_response(self, 400, {"ok": False, "error": "创作意图过长"})

        t0 = time.time()
        try:
            result = _call_deepseek(prompt)
        except Exception as e:
            return _json_response(self, 502, {"ok": False, "error": str(e)})

        result["ok"] = True
        result["latency_ms"] = int((time.time() - t0) * 1000)
        result["server_time"] = int(time.time())
        _json_response(self, 200, result)
