__all__ = [
    "BinaryEditorWindow",
    "EnumDefDictEditor",
    "StructDefDictEditor",
]


def __getattr__(name: str):
    """Lazily import GUI editor classes to avoid import-time dependency issues."""
    if name == "BinaryEditorWindow":
        from .binary_editor_window import BinaryEditorWindow
        return BinaryEditorWindow
    if name == "EnumDefDictEditor":
        from .enum_def_dict_editor import EnumDefDictEditor
        return EnumDefDictEditor
    if name == "StructDefDictEditor":
        from .struct_def_dict_editor import StructDefDictEditor
        return StructDefDictEditor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
