"""
SCG 自然语言 LLM 设置（P2）。

使用 Scene 属性配置（区域 7 面板），API Key 可保存到 Blender 用户配置目录。
不再向已注册的 ICity AddonPreferences 动态注入属性（会触发 _PropertyDeferred）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bpy

# 各厂商默认 endpoint / 模型（不含 API Key）
PROVIDERS: dict[str, tuple[str, str]] = {
    "VOLCENGINE": ("https://ark.cn-beijing.volces.com/api/v3", "deepseek-v3-250324"),
    "DEEPSEEK": ("https://api.deepseek.com", "deepseek-v4-flash"),
    "DASHSCOPE": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
    "ZHIPU": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "OPENAI": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "CUSTOM": ("", ""),
}

_CONFIG_NAME = "icity_scg_nl.json"


def _safe_str(obj: Any, attr: str, default: str = "") -> str:
    try:
        val = getattr(obj, attr, default)
    except AttributeError:
        return default
    if val is None:
        return default
    if type(val).__name__ == "_PropertyDeferred":
        return default
    return str(val).strip()


def _config_path() -> Path:
    return Path(bpy.utils.user_resource("CONFIG")) / _CONFIG_NAME


def load_persisted() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def save_persisted(data: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_provider_defaults(scene: bpy.types.Scene) -> None:
    provider = _safe_str(scene, "scg_nl_provider", "DEEPSEEK") or "DEEPSEEK"
    url, model = PROVIDERS.get(provider, ("", ""))
    if url:
        scene.scg_nl_base_url = url
    if model:
        scene.scg_nl_model = model


def on_nl_provider_change(self, _context: bpy.types.Context) -> None:
    apply_provider_defaults(self)


def sync_scene_from_disk(scene: bpy.types.Scene) -> None:
    """从本地 JSON 恢复 LLM 设置（当前场景尚无 API Key 时）。"""
    if scene is None:
        return
    if _safe_str(scene, "scg_nl_api_key"):
        return

    data = load_persisted()
    if not data:
        return

    if data.get("api_key"):
        scene.scg_nl_api_key = str(data["api_key"])
    if data.get("provider"):
        scene.scg_nl_provider = str(data["provider"])
    if data.get("base_url"):
        scene.scg_nl_base_url = str(data["base_url"])
    if data.get("model"):
        scene.scg_nl_model = str(data["model"])
    if "temperature" in data:
        try:
            scene.scg_nl_temperature = float(data["temperature"])
        except (TypeError, ValueError):
            pass
    if "debug" in data:
        scene.scg_nl_debug = bool(data["debug"])


def persist_scene_settings(scene: bpy.types.Scene) -> str:
    """将当前 Scene 上的 LLM 设置写入本地 JSON。"""
    data = {
        "api_key": _safe_str(scene, "scg_nl_api_key"),
        "provider": _safe_str(scene, "scg_nl_provider", "DEEPSEEK") or "DEEPSEEK",
        "base_url": _safe_str(scene, "scg_nl_base_url"),
        "model": _safe_str(scene, "scg_nl_model"),
        "temperature": float(getattr(scene, "scg_nl_temperature", 0.05)),
        "debug": bool(getattr(scene, "scg_nl_debug", False)),
    }
    save_persisted(data)
    return str(_config_path())


def get_nl_settings(context: bpy.types.Context | None = None) -> dict[str, Any]:
    """读取 LLM 配置（安全字符串化，避免 _PropertyDeferred）。"""
    context = context or bpy.context
    scene = context.scene
    sync_scene_from_disk(scene)

    return {
        "provider": _safe_str(scene, "scg_nl_provider", "DEEPSEEK") or "DEEPSEEK",
        "api_key": _safe_str(scene, "scg_nl_api_key"),
        "base_url": _safe_str(scene, "scg_nl_base_url"),
        "model": _safe_str(scene, "scg_nl_model"),
        "temperature": float(getattr(scene, "scg_nl_temperature", 0.05)),
        "debug": bool(getattr(scene, "scg_nl_debug", False)),
    }


def draw_nl_api_settings(layout, scene: bpy.types.Scene) -> None:
    box = layout.box()
    box.label(text="LLM API 配置", icon="SETTINGS")
    col = box.column(align=True)
    col.use_property_split = True
    col.prop(scene, "scg_nl_provider", text="提供商")
    col.prop(scene, "scg_nl_api_key", text="API Key")
    if scene.scg_nl_provider == "CUSTOM":
        col.prop(scene, "scg_nl_base_url", text="Base URL")
    col.prop(scene, "scg_nl_model", text="模型")
    col.prop(scene, "scg_nl_temperature", text="Temperature")
    col.prop(scene, "scg_nl_debug", text="调试日志")
    row = col.row(align=True)
    row.operator("scg.save_nl_api_settings", text="保存到本地", icon="FILE_TICK")
    col.label(text="保存后重启 Blender 会自动加载 Key", icon="INFO")


def register():
    pass


def unregister():
    pass
