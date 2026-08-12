"""Tests for the payload StructLayout definition editor module."""
import runpy
import types
from pathlib import Path

import sltgui.payload_struct_def_editor as editor_module
from sltgui import PayloadStructDefEditor


def test_payload_struct_def_editor_is_public():
    assert PayloadStructDefEditor.__name__ == "PayloadStructDefEditor"


def test_payload_struct_def_editor_supports_direct_script_loading(monkeypatch):
    module_path = (Path(__file__).parents[1] / "src" / "sltgui" /
                   "payload_struct_def_editor.py")
    monkeypatch.syspath_prepend(str(module_path.parent))

    namespace = runpy.run_path(module_path, run_name="direct_import_test")

    assert "PayloadStructDefEditor" in namespace


def test_select_struct_updates_selected_payload_definition(monkeypatch):
    """Select Struct changes the active StructLayout's root StructDef."""
    definition = types.SimpleNamespace(struct_layout=types.SimpleNamespace(
        struct_def_name="Header",
        type_dict=types.SimpleNamespace(struct_dict={
            "Payload": object(),
            "Header": object()
        }, ),
    ), )
    editor = object.__new__(PayloadStructDefEditor)
    editor.definitions = [definition]
    editor.current_index = 0
    editor.updated = False
    refreshes = []
    editor._refresh_tree = lambda index: refreshes.append(index)
    dialog_calls = []

    class Dialog:

        def __init__(self, parent, title, items):
            dialog_calls.append((parent, title, items))

        def show(self):
            return "Payload"

    monkeypatch.setattr(editor_module, "SelectDialog", Dialog)

    editor._select_struct_definition()

    assert dialog_calls == [(editor, "Select StructDef", [
        ("Header", "Header"),
        ("Payload", "Payload"),
    ])]
    assert definition.struct_layout.struct_def_name == "Payload"
    assert editor.updated is True
    assert refreshes == [0]
