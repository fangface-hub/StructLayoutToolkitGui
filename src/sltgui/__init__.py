"""Lazy import interface for GUI editor classes."""
import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .binary_editor_window import BinaryEditorWindow
    from .enum_def_dict_editor import EnumDefDictEditor
    from .packet_data_editor_window import PacketDataEditorWindow
    from .payload_struct_def_editor import PayloadStructDefEditor
    from .struct_def_dict_editor import StructDefDictEditor

__all__ = [
    "BinaryEditorWindow",
    "EnumDefDictEditor",
    "PacketDataEditorWindow",
    "PayloadStructDefEditor",
    "StructDefDictEditor",
]


def __getattr__(name: str):
    """Lazily import GUI editor classes to avoid import-time
    dependency issues.
    """
    if name == "BinaryEditorWindow":
        module = importlib.import_module(".binary_editor_window", __name__)
        return module.BinaryEditorWindow
    if name == "EnumDefDictEditor":
        module = importlib.import_module(".enum_def_dict_editor", __name__)
        return module.EnumDefDictEditor
    if name == "PacketDataEditorWindow":
        module = importlib.import_module(".packet_data_editor_window", __name__)
        return module.PacketDataEditorWindow
    if name == "PayloadStructDefEditor":
        module = importlib.import_module(".payload_struct_def_editor", __name__)
        return module.PayloadStructDefEditor
    if name == "StructDefDictEditor":
        module = importlib.import_module(".struct_def_dict_editor", __name__)
        return module.StructDefDictEditor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
