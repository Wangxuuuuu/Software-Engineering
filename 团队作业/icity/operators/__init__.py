# Smart City Generator — operators 包

from .apply_template import classes as apply_template_classes
from .generate_base import classes as generate_base_classes
from .icity_bridge import classes as icity_bridge_classes
from .layout_control import classes as layout_control_classes
from .road_texture import classes as road_texture_classes
from .street_lights import classes as street_lights_classes
from .scene_enhance import classes as scene_enhance_classes
from .dynamic_elements import classes as dynamic_elements_classes
from .nl_execute import classes as nl_execute_classes

_all_operator_classes = (
    icity_bridge_classes
    + generate_base_classes
    + road_texture_classes
    + street_lights_classes
    + apply_template_classes
    + layout_control_classes
    + scene_enhance_classes
    + dynamic_elements_classes
    + nl_execute_classes
)


def register():
    from bpy.utils import register_class

    for cls in _all_operator_classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(_all_operator_classes):
        unregister_class(cls)
