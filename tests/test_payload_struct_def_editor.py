"""Tests for the payload StructLayout definition editor module."""
# pylint: disable=protected-access,unnecessary-lambda
import runpy
import types
from pathlib import Path

import sltgui.payload_struct_def_editor as editor_module
from sltgui import PayloadStructDefEditor


class _EntryStub:
    """Store Entry and Combobox text without creating Tk widgets."""

    def __init__(self, value=""):
        self.value = value
        self.options = {}

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **kwargs):
        self.options.update(kwargs)


class _TreeStub:
    """Record the Treeview operations used by the payload controller."""

    def __init__(self, selected=()):
        self.rows = {}
        self.selected = list(selected)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *row_ids):
        for row_id in row_ids:
            self.rows.pop(row_id, None)

    def insert(self, _parent, _index, iid, values):
        self.rows[iid] = tuple(values)

    def selection(self):
        return tuple(self.selected)

    def selection_set(self, row_id):
        self.selected = [row_id]


class _UiWidget:
    """Accept and record common Tk widget operations."""

    def __init__(self, *_args, **kwargs):
        self.options = dict(kwargs)
        self.value = ""

    def pack(self, **_kwargs):
        return self

    def grid(self, **_kwargs):
        return self

    def configure(self, **kwargs):
        self.options.update(kwargs)

    def columnconfigure(self, *_args, **_kwargs):
        return None


class _UiTree(_UiWidget, _TreeStub):
    """Combine UI layout and Treeview recording behavior."""

    def __init__(self, *_args, **kwargs):
        _UiWidget.__init__(self, *_args, **kwargs)
        _TreeStub.__init__(self)

    def heading(self, *_args, **_kwargs):
        return None

    def column(self, *_args, **_kwargs):
        return None

    def set_readonly_column(self, *_args):
        return None

    def bind(self, *_args):
        return None


def _definition(condition="True", struct_name="Packet", struct_names=None):
    """Create a payload definition-shaped object for controller tests."""
    names = struct_names if struct_names is not None else [struct_name]
    return types.SimpleNamespace(
        condition=condition,
        struct_layout=types.SimpleNamespace(
            struct_def_name=struct_name,
            type_dict=types.SimpleNamespace(
                struct_dict={name: object()
                             for name in names}, ),
        ),
    )


def _controller(definitions=None):
    editor = object.__new__(PayloadStructDefEditor)
    editor.definitions = list(definitions or [])
    editor.current_index = None
    editor.updated = False
    editor.data_dir = Path("data")
    editor.definition_file = None
    editor.tree = _TreeStub()
    editor.condition_entry = _EntryStub()
    editor.struct_combo = _EntryStub()
    return editor


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


def test_selected_definition_checks_index_bounds():
    definition = _definition()
    editor = _controller([definition])

    assert editor._selected_definition() is None
    editor.current_index = -1
    assert editor._selected_definition() is None
    editor.current_index = 1
    assert editor._selected_definition() is None
    editor.current_index = 0
    assert editor._selected_definition() is definition


def test_refresh_tree_loads_selection_and_clears_empty_editor():
    definitions = [
        _definition("kind == 1", "Header", ["Header", "Payload"]),
        _definition("True", "Payload", ["Payload"]),
    ]
    editor = _controller(definitions)

    editor._refresh_tree(5)

    assert editor.tree.rows == {
        "0": ("kind == 1", "Header"),
        "1": ("True", "Payload"),
    }
    assert editor.current_index == 1
    assert editor.condition_entry.value == "True"
    assert editor.struct_combo.options["values"] == ["Payload"]

    editor.definitions.clear()
    editor._refresh_tree()
    assert editor.current_index is None
    assert editor.condition_entry.value == ""
    assert editor.struct_combo.options["values"] == ()


def test_tree_selection_loads_definition():
    editor = _controller([_definition("first"), _definition("second")])
    editor.tree.selected = ["1"]

    editor._on_selected(None)

    assert editor.current_index == 1
    assert editor.condition_entry.value == "second"


def test_add_remove_and_move_update_order(monkeypatch):
    first = _definition("first")
    second = _definition("second")
    editor = _controller([first, second])
    refreshes = []
    editor._refresh_tree = refreshes.append
    monkeypatch.setattr(editor_module, "TypeDict", lambda: "type-dict")
    monkeypatch.setattr(editor_module, "StructLayout", lambda name, type_dict:
                        (name, type_dict))
    monkeypatch.setattr(editor_module, "PayloadStructDef",
                        lambda condition, layout: (condition, layout))

    editor._add()
    assert editor.definitions[-1] == ("True", ("", "type-dict"))
    assert refreshes == [2]

    editor.current_index = 0
    editor._move(-1)
    assert editor.definitions[:2] == [first, second]
    editor._move(1)
    assert editor.definitions[:2] == [second, first]
    assert refreshes[-1] == 1

    editor.current_index = 1
    editor._remove()
    assert first not in editor.definitions
    assert refreshes[-1] == 1
    assert editor.updated is True


def test_update_requires_condition_then_updates_definition(monkeypatch):
    definition = _definition("old", "Old")
    editor = _controller([definition])
    editor.current_index = 0
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))
    refreshes = []
    editor._refresh_tree = refreshes.append

    editor.condition_entry.value = "  "
    editor._update()
    assert errors[0][0][:2] == ("Condition Error", "Condition is required.")

    editor.condition_entry.value = " kind == 2 "
    editor.struct_combo.value = "New"
    editor._update()
    assert definition.condition == "kind == 2"
    assert definition.struct_layout.struct_def_name == "New"
    assert editor.updated is True
    assert refreshes == [0]


def test_load_struct_layout_handles_cancel_error_and_success(monkeypatch):
    definition = _definition()
    editor = _controller([definition])
    editor.current_index = 0
    refreshes = []
    editor._refresh_tree = refreshes.append
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))

    monkeypatch.setattr(editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "")
    editor._load_struct_layout()
    assert definition.struct_layout.struct_def_name == "Packet"

    monkeypatch.setattr(editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "layouts/bad.json")
    monkeypatch.setattr(editor_module, "load_struct_layout", lambda _path:
                        (_ for _ in ()).throw(ValueError("bad")))
    editor._load_struct_layout()
    assert errors[-1][:2] == ("Load Error", "bad")

    loaded = types.SimpleNamespace(struct_def_name="Loaded")
    monkeypatch.setattr(editor_module, "load_struct_layout",
                        lambda _path: loaded)
    editor._load_struct_layout()
    assert definition.struct_layout is loaded
    assert editor.data_dir == Path("layouts")
    assert editor.updated is True
    assert refreshes == [0]


def test_select_struct_reports_missing_definition_and_struct(monkeypatch):
    editor = _controller()
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args[0]))

    editor._select_struct_definition()
    editor.definitions = [_definition(struct_names=[])]
    editor.current_index = 0
    editor._select_struct_definition()

    assert errors == ["No Definition", "No Struct"]


def test_open_type_editor_uses_selected_type_dict(monkeypatch):
    definition = _definition()
    editor = _controller([definition])
    editor.current_index = 0
    created = []
    shown = []

    class TypeEditor:

        def __init__(self, parent, type_dict):
            created.append((parent, type_dict))

    monkeypatch.setattr(
        editor_module,
        "import_module",
        lambda name: types.SimpleNamespace(TypeEditor=TypeEditor),
    )
    monkeypatch.setattr(editor_module, "show_modal_window",
                        lambda parent, modal: shown.append((parent, modal)))
    refreshes = []
    editor._refresh_tree = refreshes.append

    editor._open_type_editor("fake_editor", "TypeEditor")

    assert created == [(editor, definition.struct_layout.type_dict)]
    assert shown[0][0] is editor
    assert editor.updated is True
    assert refreshes == [0]


def test_open_replaces_definitions_and_handles_error(monkeypatch):
    editor = _controller([_definition("old")])
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    monkeypatch.setattr(editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "defs.json")
    monkeypatch.setattr(editor_module, "load_payload_struct_defs", lambda _path:
                        (_ for _ in ()).throw(ValueError("bad")))

    editor._open()
    assert errors[-1][:2] == ("Open Error", "bad")

    loaded = [_definition("loaded")]
    monkeypatch.setattr(editor_module, "load_payload_struct_defs",
                        lambda _path: loaded)
    refreshes = []
    editor._refresh_tree = refreshes.append
    editor._open()

    assert editor.definitions == loaded
    assert editor.definition_file == Path("defs.json")
    assert editor.updated is True
    assert refreshes == [0]


def test_save_and_write_paths(monkeypatch):
    editor = _controller([_definition()])
    saves = []
    infos = []
    errors = []
    monkeypatch.setattr(
        editor_module, "save_payload_struct_defs",
        lambda definitions, path: saves.append((definitions, path)))
    monkeypatch.setattr(editor_module.messagebox, "showinfo",
                        lambda *args, **kwargs: infos.append(args))
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))

    save_as_calls = []
    editor._save_as = lambda: save_as_calls.append(True)
    editor._save()
    assert save_as_calls == [True]

    editor.definition_file = Path("old.json")
    editor._save()
    assert saves[-1][1] == Path("old.json")

    monkeypatch.setattr(editor_module.filedialog, "asksaveasfilename",
                        lambda **_kwargs: "folder/new.json")
    editor._save_as = types.MethodType(PayloadStructDefEditor._save_as, editor)
    editor._save_as()
    assert editor.definition_file == Path("folder/new.json")
    assert editor.data_dir == Path("folder")
    assert infos[-1][0] == "Saved"

    monkeypatch.setattr(editor_module, "save_payload_struct_defs",
                        lambda *_args: (_ for _ in ()).throw(OSError("disk")))
    editor._write(Path("failed.json"))
    assert errors[-1][:2] == ("Save Error", "disk")


def test_unselected_operations_are_guarded(monkeypatch):
    editor = _controller([_definition()])
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args[0]))

    editor._remove()
    editor._move(1)
    editor._update()
    editor._load_struct_layout()
    editor._open_type_editor("unused", "Unused")

    assert editor.definitions[0].condition == "True"
    assert errors == ["No Definition"]


def test_editor_shortcuts_delegate_to_type_editor():
    editor = _controller()
    calls = []
    editor._open_type_editor = lambda *args: calls.append(args)

    editor._open_struct_editor()
    editor._open_enum_editor()

    assert calls == [
        ("struct_def_dict_editor", "StructDefDictEditor"),
        ("enum_def_dict_editor", "EnumDefDictEditor"),
    ]


def test_build_menu_and_ui_wire_commands(monkeypatch):
    editor = object.__new__(PayloadStructDefEditor)
    menus = []
    buttons = []

    class Menu(_UiWidget):

        def __init__(self, *_args, **kwargs):
            super().__init__(*_args, **kwargs)
            self.commands = []
            menus.append(self)

        def add_command(self, **kwargs):
            self.commands.append(kwargs)

        def add_separator(self):
            return None

        def add_cascade(self, **kwargs):
            self.options.setdefault("cascades", []).append(kwargs)

    def button_factory(*args, **kwargs):
        widget = _UiWidget(*args, **kwargs)
        buttons.append(widget)
        return widget

    monkeypatch.setattr(editor_module.tk, "Menu", Menu)
    for name in ("Frame", "Label", "LabelFrame"):
        monkeypatch.setattr(editor_module.ttk, name, _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Button", button_factory)
    monkeypatch.setattr(editor_module.ttk, "Entry", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Combobox", _UiWidget)
    monkeypatch.setattr(editor_module, "TreeviewEx", _UiTree)
    configured = []
    editor.config = lambda **kwargs: configured.append(kwargs)

    editor._build_menu()
    editor._build_ui()

    assert configured == [{"menu": menus[0]}]
    assert [command["label"] for command in menus[1].commands
            ] == ["Open...", "Save", "Save As...", "Close"]
    assert {button.options["text"]
            for button in buttons} == {
                "Add",
                "Remove",
                "Move Up",
                "Move Down",
                "Load StructLayout...",
                "Update",
            }


def test_constructor_keeps_definitions_and_initializes_state(monkeypatch):
    monkeypatch.setattr(editor_module.tk.Toplevel, "__init__",
                        lambda self, parent: None)
    monkeypatch.setattr(PayloadStructDefEditor, "withdraw", lambda self: None)
    monkeypatch.setattr(PayloadStructDefEditor, "title",
                        lambda self, value: None)
    monkeypatch.setattr(PayloadStructDefEditor, "geometry",
                        lambda self, value: None)
    monkeypatch.setattr(PayloadStructDefEditor, "_build_menu",
                        lambda self: None)

    def build_ui(editor):
        editor.tree = _TreeStub()
        editor.condition_entry = _EntryStub()
        editor.struct_combo = _EntryStub()

    monkeypatch.setattr(PayloadStructDefEditor, "_build_ui", build_ui)
    definitions = [_definition()]

    editor = PayloadStructDefEditor(object(), definitions, data_dir="layouts")

    assert editor.definitions is definitions
    assert editor.data_dir == Path("layouts")
    assert editor.definition_file is None
    assert editor.updated is False
    assert editor.tree.rows == {"0": ("True", "Packet")}


def test_main_runs_editor_as_modal(monkeypatch):
    events = []

    class Root:

        def withdraw(self):
            events.append("withdraw")

        def destroy(self):
            events.append("destroy")

    root = Root()
    modal = object()
    monkeypatch.setattr(editor_module.tk, "Tk", lambda: root)
    monkeypatch.setattr(editor_module, "PayloadStructDefEditor",
                        lambda parent: modal)
    monkeypatch.setattr(editor_module, "show_modal_window",
                        lambda parent, child: events.append((parent, child)))

    editor_module.main()

    assert events == ["withdraw", (root, modal), "destroy"]
