"""
Smart City Generator 扩展的注册入口。
由 icity/__init__.py 在 register()/unregister() 末尾调用，与 ICity 原生类分离。
"""

from __future__ import annotations


def register():
    # 显式导入子包，避免与遗留的 ui.py / operators.py 单文件冲突
    from . import scg_nl_preferences, scg_properties
    from .core.command_executor import register_default_commands
    from .operators import register as register_operators
    from .ui import register as register_ui

    register_default_commands()
    scg_nl_preferences.register()
    scg_properties.register()
    register_operators()
    register_ui()


def unregister():
    from . import scg_nl_preferences, scg_properties
    from .operators import unregister as unregister_operators
    from .ui import unregister as unregister_ui

    unregister_ui()
    unregister_operators()
    scg_properties.unregister()
    scg_nl_preferences.unregister()
