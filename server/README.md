# 创源印记 · 后端服务（真实 AI 创作）

前端为单文件网页，AI 创作能力通过后端代理 DeepSeek 大模型实现，**API Key 只保存在服务端环境变量中，不写进前端代码**。

## 一、本地运行（零依赖，推荐评审复现）

需要 Python 3.8 及以上，无需 pip 安装任何包。

```bash
# 1. 进入 server 目录
cd server

# 2. 设置 DeepSeek API Key（二选一）
# Windows PowerShell：
$env:DEEPSEEK_API_KEY="sk-你的key"
# macOS / Linux：
export DEEPSEEK_API_KEY="sk-你的key"

# 3. 启动
python app.py        # （部分系统为 python3 app.py）
```

启动后浏览器打开 **http://localhost:8090** ，前端与 AI 接口同源，开箱即用。

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/generate` | POST | 入参 `{"prompt":"创作意图"}`，返回真实 AI 生成内容、模型名、token 用量与耗时 |

未设置 API Key 时，前端仍可打开，「真实 AI 生成」会自动降级为内置本地演示文案，其余指纹、验证功能不受影响。

## 二、线上部署（Vercel，免费额度足够演示）

1. 将本 GitHub 仓库导入 Vercel（New Project → Import）。
2. **Settings → Environment Variables** 新增：
   - `DEEPSEEK_API_KEY` = `sk-xxxx`（必填）
   - `DEEPSEEK_MODEL` = `deepseek-chat`（可选，默认即此值）
3. Deploy。根路由自动指向 `prototype/index.html`，`api/generate.py` 自动成为 Serverless 接口 `/api/generate`。
4. 部署完成后把 Vercel 域名填到前端「后端地址」设置中（默认同源，留空即可）。

> 仓库根目录的 `vercel.json` 已配置静态托管与接口路由；`api/generate.py` 仅用 Python 标准库。

## 三、文件说明

| 文件 | 作用 |
| --- | --- |
| `app.py` | 本地服务器：静态托管 `../prototype` + 代理 DeepSeek |
| `../api/generate.py` | Vercel Serverless 函数，逻辑与本地服务器一致 |
| `../vercel.json` | Vercel 路由配置 |
| `../requirements.txt` | 声明零第三方依赖 |

## 四、安全说明

- API Key 仅通过服务端环境变量读取，前端代码、Git 仓库中均不含密钥。
- 接口对创作意图长度做了限制（≤2000 字），并设置了 60s 超时与错误兜底。
- 本项目为参赛概念验证，正式生产时应增加鉴权、限流与调用配额。
