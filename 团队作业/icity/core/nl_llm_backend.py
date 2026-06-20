"""
LLM 后端 — OpenAI 兼容 /chat/completions（P2）。

纯 urllib，零第三方依赖。输出格式见 团队作业/插件命令协议.md
"""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Any, Optional

from ..scg_nl_preferences import get_nl_settings

# P0/P1 已注册 action（与 nl_handlers 同步）
VALID_ACTIONS = frozenset({
    "apply_template",
    "apply_asset_config",
    "set_road_texture",
    "set_environment",
    "add_dynamic_element",
    "add_street_lights",
})

# 旧 NLP fn → SCG action 最小映射（联调容错）
_FN_TO_ACTION = {
    "apply_template": "apply_template",
    "set_environment": "set_environment",
    "set_road_texture": "set_road_texture",
    "add_dynamic_element": "add_dynamic_element",
    "add_street_lights": "add_street_lights",
}

SYSTEM_PROMPT = r"""你是 Blender Smart City Generator (SCG) 程序化城市场景编辑助手。
用户用**自然语言**描述对城市的修改，你输出**一段合法 JSON**，不要 markdown、不要额外说明文字。

━━━ 输出格式（严格遵守）━━━
{
  "commands": [
    { "action": "<action_name>", "params": { } }
  ],
  "reply": "<一句话中文摘要，供 UI 显示>"
}

━━━ 可用 action ━━━

1. apply_template — 应用 config/templates.json 中的模板并生成城市
   params: { "template_id": "0" }
   template_id 为字符串 "0"、"1" 等

2. apply_asset_config — 设置树木/道路/座椅类型并可重新生成
   params: {
     "tree_type": 1,
     "road_texture": 1,
     "bench_type": 1,
     "regenerate": true
   }
   tree_type / road_texture / bench_type 取值 1 或 2

3. set_road_texture — 仅更换道路纹理（不整城重建）
   params: { "type": 1 }
   type 取值 1 或 2

4. set_environment — 昼夜 / 雨天
   params: { "mode": "day" | "night" | "rainy" }
   变暗/夜间/夜晚 → night；白天/天亮 → day；雨天/下雨 → rainy

5. add_dynamic_element — 添加车辆 / 行人 / 船只
   params: { "type": "car" | "pedestrian" | "boat", "count": 2 }
   添加车辆时 type 必须为 "car"，count 为车辆数量（仅车，不含行人）

6. add_street_lights — 添加路灯（扩展）
   params: { "night_emission": false }

━━━ 规则 ━━━
• 一条用户话可对应多个 commands，按数组顺序执行
• 只使用上述 action，不要输出 fn、intent、actions 等旧字段
• params 缺省时用 {}
• 无法理解时：{"commands": [], "reply": "无法理解：…"}
• reply 必须使用中文
"""


def _chat_completions_url(base_url: str) -> str:
    """拼接 OpenAI 兼容的 chat/completions 地址。"""
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith(("/v1", "/v3", "/v4")):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _log(msg: str) -> None:
    settings = get_nl_settings()
    if settings.get("debug"):
        print(f"[SCG LLM] {msg}")


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text


def _normalize_mode(params: dict[str, Any]) -> dict[str, Any]:
    mode = str(params.get("mode", "")).lower()
    alias = {
        "dark": "night",
        "dusk": "night",
        "night": "night",
        "day": "day",
        "rainy": "rainy",
        "rain": "rainy",
    }
    if mode in alias:
        params = dict(params)
        params["mode"] = alias[mode]
    return params


def _normalize_command(cmd: Any) -> Optional[dict[str, Any]]:
    if not isinstance(cmd, dict):
        return None

    action = str(cmd.get("action", "")).strip()
    params = cmd.get("params")
    if params is None:
        params = cmd.get("args")
    if not isinstance(params, dict):
        params = {}

    # 旧 NLP actions[] 容错
    if not action and cmd.get("fn"):
        fn = str(cmd["fn"])
        action = _FN_TO_ACTION.get(fn, fn)
        params = cmd.get("args") if isinstance(cmd.get("args"), dict) else params

    if action == "apply_template" and "template_id" not in params:
        for key in ("id", "template", "templateId"):
            if key in params:
                params = dict(params)
                params["template_id"] = str(params.pop(key))
                break

    if action == "set_road_texture" and "type" not in params:
        for key in ("road_type", "road_texture", "texture"):
            if key in params:
                params = dict(params)
                params["type"] = int(params.pop(key))
                break

    if action == "set_environment":
        params = _normalize_mode(params)

    if action not in VALID_ACTIONS:
        return None

    return {"action": action, "params": params}


def normalize_llm_response(data: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """将 LLM 原始 JSON 规范为 command_executor 可用的 payload。"""
    commands_raw = data.get("commands")
    if not isinstance(commands_raw, list):
        actions_raw = data.get("actions")
        if isinstance(actions_raw, list):
            commands_raw = actions_raw
        else:
            commands_raw = []

    commands: list[dict[str, Any]] = []
    for item in commands_raw:
        normalized = _normalize_command(item)
        if normalized:
            commands.append(normalized)

    reply = str(data.get("reply") or "").strip()
    if not reply:
        if commands:
            names = ", ".join(c["action"] for c in commands)
            reply = f"已解析：{names}"
        else:
            reply = "LLM 未返回有效 commands"

    return {
        "source": "llm",
        "raw_text": raw_text,
        "commands": commands,
        "reply": reply,
    }


def call_llm(user_text: str) -> dict[str, Any]:
    """调用 LLM，返回解析后的 JSON dict。"""
    settings = get_nl_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        raise ValueError(
            "请先在 Smart City 区域 7 展开 LLM API 配置，填写 API Key 并点「保存到本地」"
        )

    base_url = (settings.get("base_url") or "").rstrip("/")
    model = (settings.get("model") or "").strip()
    temperature = float(settings.get("temperature", 0.05))
    provider = settings.get("provider", "DEEPSEEK")

    if not base_url or not model:
        raise ValueError("请配置 LLM Base URL 与模型名称")

    url = _chat_completions_url(base_url)
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    }
    if provider in ("DEEPSEEK", "OPENAI", "VOLCENGINE"):
        payload["response_format"] = {"type": "json_object"}

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    ctx = ssl.create_default_context()

    _log(f"POST {url} model={model}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise ConnectionError(f"HTTP {exc.code}: {err[:400]}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"网络错误: {exc.reason}") from exc

    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ConnectionError(f"LLM 返回格式异常: {str(raw)[:300]}") from exc

    _log(f"Response: {content[:300]}")
    text = _strip_json_fence(str(content))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        # 尝试从文本中提取首个 JSON 对象
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ConnectionError(f"LLM 返回非 JSON: {text[:200]}") from exc
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ConnectionError("LLM 返回必须是 JSON 对象")

    return parsed


def call_llm_and_to_payload(user_text: str) -> dict[str, Any]:
    """调用 LLM 并规范为 SCG commands payload。"""
    raw = call_llm(user_text)
    payload = normalize_llm_response(raw, user_text)
    if not payload.get("commands"):
        raise ValueError(payload.get("reply") or "LLM 未返回可执行 commands")
    return payload
