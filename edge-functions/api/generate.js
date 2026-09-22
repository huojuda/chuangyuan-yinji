/**
 * 创源印记 · EdgeOne Makers 边缘函数 —— 真实 AI 创作接口（后端）
 *
 * 路由（由文件路径自动生成，无需配置）：
 *   POST /api/generate   真实生成（代理 DeepSeek）
 *   GET  /api/generate   健康探针，返回 JSON（用于判断函数是否真的注册成功）
 *   OPTIONS /api/generate  预检
 *
 * 运行环境：EdgeOne Makers Edge Functions（V8 隔离环境，非 Node.js）
 * 可用能力：fetch / Web Crypto / TextEncoder / Response / Request —— 全部为 Web 标准 API
 * 第三方依赖：无（不使用 require、process、fs、npm 包）
 *
 * 需在 EdgeOne Makers 控制台 → 项目设置 → 环境变量 配置：
 *   DEEPSEEK_API_KEY    必需，DeepSeek 密钥（建议设为「加密」类型）
 *   DEEPSEEK_ENDPOINT   可选，默认 https://api.deepseek.com/chat/completions
 *   DEEPSEEK_MODEL      可选，默认 deepseek-chat
 *   ALLOW_ORIGINS       可选，逗号分隔的 Origin 白名单。配置后 POST 仅接受名单内来源，
 *                       用于防止该接口被外部站点/脚本盗用烧 key；不配置则不限制。
 */

const DEFAULT_ENDPOINT = 'https://api.deepseek.com/chat/completions';
const DEFAULT_MODEL = 'deepseek-chat';
const MAX_PROMPT_LEN = 2000;

const SYSTEM_PROMPT =
  '你是「创源印记」AI 原生创作确权体系中的创作引擎。用户会给出一个创作意图，' +
  '你需要直接产出成品内容，不要解释、不要前后缀寒暄、不要使用 Markdown 代码块。\n' +
  '根据创作意图判断体裁：\n' +
  '- 若要求诗歌/短诗，输出 4-8 行中文现代诗，意象鲜明；\n' +
  '- 若要求海报/视觉/设计方案，输出结构化的视觉方案（主视觉、主标题、副标题、配色、构图要点），每行一条；\n' +
  '- 若要求广告/旁白/文案，输出可直接朗读的文案，控制在 80 字以内；\n' +
  '- 其他体裁按用户要求产出精炼成品，控制在 200 字以内。\n' +
  '只输出作品正文本身。';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Max-Age': '86400',
};

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: Object.assign(
      {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
      CORS_HEADERS
    ),
  });
}

function envOf(context) {
  return (context && context.env) || {};
}

/** Origin 白名单校验：未配置 ALLOW_ORIGINS 时放行（向后兼容）。 */
function originAllowed(context) {
  const allow = String(envOf(context).ALLOW_ORIGINS || '').trim();
  if (!allow) return true;
  const list = allow
    .split(',')
    .map(function (s) {
      return s.trim().replace(/\/+$/, '');
    })
    .filter(Boolean);
  const origin = (context.request.headers.get('Origin') || '').replace(/\/+$/, '');
  return origin !== '' && list.indexOf(origin) >= 0;
}

function stripFences(s) {
  return String(s || '')
    .trim()
    .replace(/^```[a-zA-Z]*\s*/, '')
    .replace(/```$/, '')
    .trim();
}

async function callDeepSeek(prompt, context) {
  const env = envOf(context);
  const apiKey = env.DEEPSEEK_API_KEY || '';
  if (!apiKey) throw new Error('服务端未配置 DEEPSEEK_API_KEY 环境变量');
  const endpoint = env.DEEPSEEK_ENDPOINT || DEFAULT_ENDPOINT;
  const model = env.DEEPSEEK_MODEL || DEFAULT_MODEL;

  const resp = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + apiKey,
    },
    body: JSON.stringify({
      model: model,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: prompt },
      ],
      stream: false,
      temperature: 0.9,
      max_tokens: 600,
    }),
  });

  const raw = await resp.text();
  if (!resp.ok) {
    throw new Error('DeepSeek API 错误 ' + resp.status + ': ' + raw.slice(0, 400));
  }
  let body;
  try {
    body = JSON.parse(raw);
  } catch (e) {
    throw new Error('DeepSeek 返回非 JSON 内容');
  }
  const choice = (body.choices || [{}])[0] || {};
  const content = (choice.message || {}).content || '';
  return {
    content: stripFences(content),
    model: body.model || model,
    usage: body.usage || {},
    id: body.id || '',
  };
}

async function handler(context) {
  const method = (context.request.method || 'GET').toUpperCase();

  if (method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  // 健康探针：函数若未注册成功，该路径会回落到静态资源并返回 HTML，据此可判定注册状态
  if (method === 'GET') {
    return jsonResponse({
      ok: true,
      service: 'chuangyuan-yinji / api/generate',
      runtime: 'edgeone-makers-edge-function',
      key_configured: !!envOf(context).DEEPSEEK_API_KEY,
      origin_restricted: !!String(envOf(context).ALLOW_ORIGINS || '').trim(),
    });
  }

  if (method !== 'POST') {
    return jsonResponse({ ok: false, error: '仅支持 POST / GET / OPTIONS' }, 405);
  }

  if (!originAllowed(context)) {
    return jsonResponse({ ok: false, error: '来源不在 ALLOW_ORIGINS 白名单内' }, 403);
  }

  let params;
  try {
    params = await context.request.json();
  } catch (e) {
    return jsonResponse({ ok: false, error: '请求体解析失败，需为 JSON' }, 400);
  }

  const prompt = String((params && params.prompt) || '').trim();
  if (!prompt) return jsonResponse({ ok: false, error: '缺少 prompt 字段' }, 400);
  if (prompt.length > MAX_PROMPT_LEN) {
    return jsonResponse({ ok: false, error: '创作意图过长（>' + MAX_PROMPT_LEN + ' 字）' }, 400);
  }

  const t0 = Date.now();
  try {
    const result = await callDeepSeek(prompt, context);
    result.ok = true;
    result.latency_ms = Date.now() - t0;
    result.server_time = Math.floor(Date.now() / 1000);
    return jsonResponse(result, 200);
  } catch (e) {
    return jsonResponse({ ok: false, error: String((e && e.message) || e) }, 502);
  }
}

export default handler;
export const onRequest = handler;
