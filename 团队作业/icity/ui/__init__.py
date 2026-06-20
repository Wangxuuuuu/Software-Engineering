# Smart City Generator — UI 模块

from .panel_smart_city import classes as panel_classes


def register():
    from bpy.utils import register_class

    for cls in panel_classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(panel_classes):
        unregister_class(cls)
