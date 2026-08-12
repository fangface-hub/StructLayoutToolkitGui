"""Tests for the EnumDefDictEditor class."""
# pylint: disable=duplicate-code,protected-access
import importlib
import sys
import types

import pytest


class _ValueWidget:
    """Store the value exposed by EntryEx and TextEx."""

    def __init__(self, value=""):
        self.value = value


class _TreeStub:
    """Record the subset of Treeview operations used by the controller."""

    def __init__(self, rows=None, selected=()):
        self.rows = dict(rows or {})
        self.selected = list(selected)
        self.focused = None
        self.seen = None

    def get_children(self):
        return tuple(self.rows)

    def insert(self, _parent, index, iid, values):
        if index == "end":
            self.rows[iid] = tuple(values)
            return
        items = list(self.rows.items())
        items.insert(index, (iid, tuple(values)))
        self.rows = dict(items)

    def delete(self, *row_ids):
        for row_id in row_ids:
            self.rows.pop(row_id, None)

    def item(self, row_id, option=None, **kwargs):
        if "values" in kwargs:
            self.rows[row_id] = tuple(kwargs["values"])
        if option == "values":
            return self.rows[row_id]
        return {"values": self.rows[row_id]}

    def selection(self):
        return tuple(self.selected)

    def selection_set(self, row_id):
        self.selected = [row_id]

    def focus(self, row_id):
        self.focused = row_id

    def see(self, row_id):
        self.seen = row_id


class _UiWidget:
    """Accept and record common Tk widget operations."""

    def __init__(self, *_args, **kwargs):
        self.options = dict(kwargs)
        self.value = ""
        self.destroyed = False

    def pack(self, **_kwargs):
        return self

    def grid(self, **_kwargs):
        return self

    def add(self, *_args, **_kwargs):
        return None

    def configure(self, *args, **kwargs):
        if args and isinstance(args[0], dict):
            self.options.update(args[0])
        self.options.update(kwargs)

    def columnconfigure(self, *_args, **_kwargs):
        return None

    def title(self, value):
        self.options["title"] = value

    def resizable(self, *value):
        self.options["resizable"] = value

    def destroy(self):
        self.destroyed = True

    def focus_set(self):
        self.options["focused"] = True


def _load_enum_editor_module(monkeypatch):
    """Load the enum_def_dict_editor module with monkeypatched dependencies.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    sltcodec_module = types.ModuleType("sltcodec")
    sltcodec_module.__path__ = []
    sltcodec_module.EnumDef = object
    sltcodec_module.TypeDict = lambda: types.SimpleNamespace(enum_dict={},
                                                             struct_dict={})
    sltcodec_module.StructLayout = (
        lambda struct_def_name, type_dict: types.SimpleNamespace(
            struct_def_name=struct_def_name,
            type_dict=type_dict,
        ))
    sltcodec_module.load_struct_layout = (
        lambda *args, **kwargs: types.SimpleNamespace(
            struct_def_name="StructLayout",
            type_dict=types.SimpleNamespace(enum_dict={}, struct_dict={}),
        ))
    sltcodec_module.save_struct_layout = lambda *args, **kwargs: None

    tkinterex_module = types.ModuleType("tkinterex")
    tkinterex_module.EntryEx = object
    tkinterex_module.TextEx = object
    tkinterex_module.show_modal_window = lambda parent, modal_window: None

    treeviewex_module = types.ModuleType("treeviewex")
    treeviewex_module.TreeviewEx = object

    monkeypatch.setitem(sys.modules, "sltcodec", sltcodec_module)
    monkeypatch.setitem(sys.modules, "tkinterex", tkinterex_module)
    monkeypatch.setitem(sys.modules, "treeviewex", treeviewex_module)
    sys.modules.pop("sltgui.enum_def_dict_editor", None)

    return importlib.import_module("sltgui.enum_def_dict_editor")


def test_enum_editor_module_and_class_exist(monkeypatch):
    """Test that the enum editor module and class exist.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules."""
    module = _load_enum_editor_module(monkeypatch)

    assert hasattr(module, "EnumDefDictEditor")


def test_enum_row_values_are_parsed_into_dictionary(monkeypatch):
    """Test that row values are parsed into a dictionary.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    sltcodec_module = types.ModuleType("sltcodec")
    sltcodec_module.__path__ = []
    sltcodec_module.EnumDef = object
    sltcodec_module.StructDef = object
    sltcodec_module.decode = lambda *args, **kwargs: None
    sltcodec_module.encode = lambda *args, **kwargs: None
    sltcodec_module.TypeDict = lambda: types.SimpleNamespace(enum_dict={},
                                                             struct_dict={})
    sltcodec_module.StructLayout = (
        lambda struct_def_name, type_dict: types.SimpleNamespace(
            struct_def_name=struct_def_name,
            type_dict=type_dict,
        ))
    sltcodec_module.load_struct_layout = (
        lambda *args, **kwargs: types.SimpleNamespace(
            struct_def_name="StructLayout",
            type_dict=types.SimpleNamespace(enum_dict={}, struct_dict={}),
        ))
    sltcodec_module.save_struct_layout = lambda *args, **kwargs: None

    tkinterex_module = types.ModuleType("tkinterex")
    tkinterex_module.EntryEx = object
    tkinterex_module.TextEx = object
    tkinterex_module.show_modal_window = lambda parent, modal_window: None

    treeviewex_module = types.ModuleType("treeviewex")
    treeviewex_module.TreeviewEx = object

    monkeypatch.setitem(sys.modules, "sltcodec", sltcodec_module)
    monkeypatch.setitem(sys.modules, "tkinterex", tkinterex_module)
    monkeypatch.setitem(sys.modules, "treeviewex", treeviewex_module)
    sys.modules.pop("sltgui", None)
    sys.modules.pop("sltgui.enum_def_dict_editor", None)

    module = importlib.import_module("sltgui.enum_def_dict_editor")

    parse = getattr(module.EnumDefDictEditor, "_row_map_to_value_dict")
    parsed = parse({
        "name": "READY",
        "value": "1",
    })

    assert parsed == {"READY": 1}


def test_enum_editor_update_preserves_struct_definitions(monkeypatch):
    """Test that updating enums preserves struct definitions.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    module = _load_enum_editor_module(monkeypatch)
    struct_def = object()
    destroyed = []
    editor = object.__new__(module.EnumDefDictEditor)
    editor.type_dict = types.SimpleNamespace(
        enum_dict={},
        struct_dict={"Packet": struct_def},
    )
    editor._flush_current_editor = lambda: True
    editor._to_enum_def_dict = lambda: {"Status": object()}
    editor.destroy = lambda: destroyed.append(True)

    editor._on_update()

    assert destroyed == [True]
    assert editor.type_dict.struct_dict["Packet"] is struct_def
    assert "Status" in editor.type_dict.enum_dict


def test_add_value_uses_start_value_then_increments_last_value(monkeypatch):
    """Test that Add Value starts at the configured value and increments."""
    module = _load_enum_editor_module(monkeypatch)

    class DummyValueTree:
        """A minimal value tree stub for Add Value."""

        def __init__(self):
            self.rows = []
            self.selected = []

        def get_children(self):
            return [row_id for row_id, _ in self.rows]

        def item(self, row_id, _option):
            return dict(self.rows)[row_id]

        def selection(self):
            return tuple(self.selected)

        def insert(self, _parent, _index, iid, values):
            row = (iid, values)
            if _index == "end":
                self.rows.append(row)
            else:
                self.rows.insert(_index, row)

    class DummyEntry:
        """A minimal EntryEx stub for the configured start value."""

        value = "10"

    editor = object.__new__(module.EnumDefDictEditor)
    editor.current_enum_key = "Status"
    editor.value_tree = DummyValueTree()
    editor.start_value_entry = DummyEntry()

    editor._add_value()
    editor._add_value()

    assert editor.value_tree.rows == [
        ("value-1", ("VALUE_1", "10")),
        ("value-2", ("VALUE_2", "11")),
    ]


def test_insert_value_uses_previous_value_plus_one(monkeypatch):
    """Test that Insert Value inserts before the topmost selected row."""
    module = _load_enum_editor_module(monkeypatch)

    class DummyValueTree:
        """A minimal value tree stub for Insert Value."""

        def __init__(self):
            self.rows = [
                ("value-1", ("VALUE_1", "10")),
                ("value-2", ("VALUE_2", "20")),
            ]
            self.selected = ["value-2"]

        def get_children(self):
            return [row_id for row_id, _ in self.rows]

        def selection(self):
            return tuple(self.selected)

        def item(self, row_id, _option):
            return dict(self.rows)[row_id]

        def insert(self, _parent, index, iid, values):
            self.rows.insert(index, (iid, values))

    editor = object.__new__(module.EnumDefDictEditor)
    editor.current_enum_key = "Status"
    editor.value_tree = DummyValueTree()
    editor._insert_value()

    assert editor.value_tree.rows == [
        ("value-1", ("VALUE_1", "10")),
        ("value-3", ("VALUE_3", "11")),
        ("value-2", ("VALUE_2", "20")),
    ]


def test_shift_selected_values_applies_signed_amount(monkeypatch):
    """Test that Shift Value applies a signed amount to selected rows."""
    module = _load_enum_editor_module(monkeypatch)

    class DummyValueTree:
        """A minimal value tree stub for Shift Value."""

        def __init__(self):
            self.rows = {
                "value-1": ["VALUE_1", "10"],
                "value-2": ["VALUE_2", "20"],
            }

        def selection(self):
            return ("value-1", "value-2")

        def item(self, row_id, _option=None, **kwargs):
            if "values" in kwargs:
                self.rows[row_id] = list(kwargs["values"])
            return self.rows[row_id]

    editor = object.__new__(module.EnumDefDictEditor)
    editor.value_tree = DummyValueTree()
    editor._ask_value_shift = lambda: module._ValueShift("-", 3)

    editor._shift_selected_values()

    assert editor.value_tree.rows == {
        "value-1": ["VALUE_1", "7"],
        "value-2": ["VALUE_2", "17"],
    }


def test_add_enum_uses_start_value_for_first_member(monkeypatch):
    """Test that Add Enum uses Start Value for VALUE_0."""
    module = _load_enum_editor_module(monkeypatch)

    class DummyEntry:
        """A minimal EntryEx stub for the configured start value."""

        value = "0x20"

    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {}
    editor.start_value_entry = DummyEntry()
    editor._flush_current_editor = lambda: True
    editor._refresh_enum_tree = lambda: None
    editor._select_enum = lambda _key: None

    editor._add_enum()

    assert editor.enum_data["Enum1"]["values"] == {"VALUE_0": 32}


def test_load_type_dict_data_selects_first_enum_or_clears(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {
        "Status": {
            "name": "Status",
            "description": "state",
            "values": {
                "READY": 1
            },
        }
    }
    editor.enum_tree = _TreeStub()
    editor.value_tree = _TreeStub()
    editor.name_entry = _ValueWidget()
    editor.description_text = _ValueWidget()

    editor._load_type_dict_data()

    assert editor.current_enum_key == "Status"
    assert editor.name_entry.value == "Status"
    assert editor.description_text.value == "state"
    assert editor.value_tree.rows == {"value-READY": ("READY", "1")}
    assert editor.enum_tree.selected == ["Status"]

    editor.enum_data.clear()
    editor._load_type_dict_data()

    assert editor.current_enum_key is None
    assert editor.name_entry.value == ""
    assert editor.value_tree.rows == {}


def test_enum_selection_flushes_before_loading(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_tree = _TreeStub(selected=("Second", ))
    editor.current_enum_key = "First"
    loaded = []
    editor._load_enum_to_editor = loaded.append
    editor._flush_current_editor = lambda: False

    editor._on_enum_selected(None)
    assert loaded == []

    editor._flush_current_editor = lambda: True
    editor._on_enum_selected(None)
    assert loaded == ["Second"]


@pytest.mark.parametrize(
    ("name", "rows", "expected_message"),
    [
        ("", {
            "value-1": ("READY", "1")
        }, "Enum name cannot be empty."),
        ("Other", {
            "value-1": ("READY", "1")
        }, "already exists"),
        ("Status", {
            "value-1": ("", "1")
        }, "member name cannot be empty"),
        ("Status", {
            "value-1": ("READY", "bad")
        }, "Invalid integer"),
    ],
)
def test_flush_current_editor_rejects_invalid_data(monkeypatch, name, rows,
                                                   expected_message):
    module = _load_enum_editor_module(monkeypatch)
    errors = []
    monkeypatch.setattr(
        module.messagebox, "showerror",
        lambda title, message, **_kwargs: errors.append((title, message)))
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {
        "Status": {
            "name": "Status",
            "values": {}
        },
        "Other": {
            "name": "Other",
            "values": {}
        },
    }
    editor.current_enum_key = "Status"
    editor.name_entry = _ValueWidget(name)
    editor.description_text = _ValueWidget("description")
    editor.value_tree = _TreeStub(rows)
    editor.enum_tree = _TreeStub()

    assert editor._flush_current_editor() is False
    assert expected_message in errors[0][1]


def test_flush_current_editor_renames_enum_and_parses_values(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {"Status": {"name": "Status", "values": {}}}
    editor.current_enum_key = "Status"
    editor.name_entry = _ValueWidget("State")
    editor.description_text = _ValueWidget("packet state")
    editor.value_tree = _TreeStub({"value-1": ("READY", "0x10")})
    editor.enum_tree = _TreeStub()

    assert editor._flush_current_editor() is True
    assert editor.enum_data == {
        "State": {
            "name": "State",
            "description": "packet state",
            "values": {
                "READY": 16
            },
        }
    }
    assert editor.current_enum_key == "State"
    assert editor.enum_tree.selected == ["State"]


def test_remove_enum_selects_remaining_item_then_clears_last(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {
        "First": {
            "name": "First",
            "values": {}
        },
        "Second": {
            "name": "Second",
            "values": {}
        },
    }
    editor.current_enum_key = "Second"
    editor.enum_tree = _TreeStub(selected=("Second", ))
    editor.value_tree = _TreeStub()
    editor.name_entry = _ValueWidget()
    editor.description_text = _ValueWidget()

    editor._remove_enum()
    assert editor.current_enum_key == "First"
    assert list(editor.enum_data) == ["First"]

    editor.enum_tree.selection_set("First")
    editor._remove_enum()
    assert editor.current_enum_key is None
    assert editor.enum_data == {}
    assert editor.name_entry.value == ""


def test_value_operations_report_missing_selection_and_bad_numbers(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    errors = []
    monkeypatch.setattr(module.messagebox, "showerror",
                        lambda title, message, **_kwargs: errors.append(title))
    editor = object.__new__(module.EnumDefDictEditor)
    editor.current_enum_key = None
    editor.value_tree = _TreeStub()
    editor.start_value_entry = _ValueWidget("invalid")

    editor._add_value()
    editor._insert_value()
    editor._shift_selected_values()

    editor.current_enum_key = "Status"
    editor._add_value()
    editor._insert_value()

    editor.value_tree = _TreeStub({"value-1": ("READY", "bad")},
                                  selected=("value-1", ))
    editor._ask_value_shift = lambda: module._ValueShift("+", 2)
    editor._shift_selected_values()

    assert errors == [
        "No Enum",
        "No Enum",
        "No Values Selected",
        "Add Value Error",
        "No Value Selected",
        "Shift Value Error",
    ]


def test_remove_value_deletes_every_selected_row(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.value_tree = _TreeStub(
        {
            "value-1": ("ONE", "1"),
            "value-2": ("TWO", "2")
        },
        selected=("value-1", "value-2"),
    )

    editor._remove_value()

    assert editor.value_tree.rows == {}


def test_update_enum_meta_renames_and_preserves_values(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {
        "Status": {
            "name": "Status",
            "description": "old",
            "values": {
                "READY": 1
            },
        }
    }
    editor.current_enum_key = "Status"
    editor.name_entry = _ValueWidget("State")
    editor.description_text = _ValueWidget("new")
    editor.enum_tree = _TreeStub()
    editor.value_tree = _TreeStub()

    assert editor._update_enum_meta() is True
    assert editor.enum_data["State"] == {
        "name": "State",
        "description": "new",
        "values": {
            "READY": 1
        },
    }
    assert editor.enum_tree.selected == ["State"]


def test_cancel_and_failed_update_have_expected_lifecycle(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    destroyed = []
    editor.destroy = lambda: destroyed.append(True)
    editor._flush_current_editor = lambda: False

    editor._on_update()
    assert destroyed == []

    editor._on_cancel()
    assert destroyed == [True]


def test_build_ui_wires_editor_widgets_and_commands(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    buttons = []

    class UiTree(_UiWidget, _TreeStub):

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

    def button_factory(*args, **kwargs):
        widget = _UiWidget(*args, **kwargs)
        buttons.append(widget)
        return widget

    for name in ("Frame", "Label", "LabelFrame", "Panedwindow"):
        monkeypatch.setattr(module.ttk, name, _UiWidget)
    monkeypatch.setattr(module.ttk, "Button", button_factory)
    monkeypatch.setattr(module.ttk, "Style", _UiWidget)
    monkeypatch.setattr(module, "EntryEx", _UiWidget)
    monkeypatch.setattr(module, "TextEx", _UiWidget)
    monkeypatch.setattr(module, "TreeviewEx", UiTree)
    editor = object.__new__(module.EnumDefDictEditor)

    editor._build_ui()

    assert editor.start_value_entry.value == "0"
    assert {button.options["text"]
            for button in buttons} == {
                "Update",
                "Cancel",
                "Add Enum",
                "Remove Enum",
                "Update Meta",
                "Add Value",
                "Insert Value",
                "Shift Value",
                "Remove Value",
            }


def test_value_shift_dialog_returns_applied_value(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    buttons = []
    entry = _UiWidget()

    class StringVar:

        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    def button_factory(*args, **kwargs):
        widget = _UiWidget(*args, **kwargs)
        buttons.append(widget)
        return widget

    monkeypatch.setattr(module.tk, "Toplevel", _UiWidget)
    monkeypatch.setattr(module.tk, "StringVar", StringVar)
    monkeypatch.setattr(module.ttk, "Label", _UiWidget)
    monkeypatch.setattr(module.ttk, "Combobox", _UiWidget)
    monkeypatch.setattr(module.ttk, "Button", button_factory)
    monkeypatch.setattr(module, "EntryEx", lambda *_args, **_kwargs: entry)

    def show_modal(_parent, _dialog):
        entry.value = "0x10"
        next(button for button in buttons
             if button.options["text"] == "Apply").options["command"]()

    monkeypatch.setattr(module, "show_modal_window", show_modal)
    editor = object.__new__(module.EnumDefDictEditor)

    assert editor._ask_value_shift() == module._ValueShift("+", 16)


def test_constructor_copies_enum_data_and_loads_first_item(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    monkeypatch.setattr(module.tk.Toplevel, "__init__",
                        lambda self, parent: None)
    monkeypatch.setattr(module.EnumDefDictEditor, "withdraw", lambda self: None)
    monkeypatch.setattr(module.EnumDefDictEditor, "title",
                        lambda self, value: None)
    monkeypatch.setattr(module.EnumDefDictEditor, "winfo_screenwidth",
                        lambda self: 1200)
    monkeypatch.setattr(module.EnumDefDictEditor, "winfo_screenheight",
                        lambda self: 800)
    geometries = []
    monkeypatch.setattr(module.EnumDefDictEditor, "geometry",
                        lambda self, value: geometries.append(value))

    def build_ui(editor):
        editor.enum_tree = _TreeStub()
        editor.value_tree = _TreeStub()
        editor.name_entry = _ValueWidget()
        editor.description_text = _ValueWidget()

    monkeypatch.setattr(module.EnumDefDictEditor, "_build_ui", build_ui)
    enum_def = types.SimpleNamespace(to_dict=lambda: {
        "name": "Status",
        "description": "",
        "values": {
            "OK": 0
        }
    })
    type_dict = types.SimpleNamespace(enum_dict={"Status": enum_def})

    editor = module.EnumDefDictEditor(object(), type_dict)

    assert geometries == ["1100x680"]
    assert editor.current_enum_key == "Status"
    assert editor.enum_data["Status"]["values"] == {"OK": 0}


def test_selection_and_flush_guard_branches(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {"Status": {"name": "Status", "values": {}}}
    editor.enum_tree = _TreeStub()
    editor.value_tree = _TreeStub()
    editor.name_entry = _ValueWidget("Status")
    editor.description_text = _ValueWidget("same")
    editor.current_enum_key = "Status"

    editor._on_enum_selected(None)
    editor.enum_tree.selected = ["Status"]
    editor._on_enum_selected(None)
    editor._select_enum("Missing")
    editor._load_enum_to_editor("Missing")
    assert editor.current_enum_key is None

    assert editor._flush_current_editor() is True
    editor.current_enum_key = "Missing"
    assert editor._flush_current_editor() is True
    assert editor.current_enum_key is None

    editor.current_enum_key = "Status"
    editor.name_entry.value = "Status"
    editor.description_text.value = "same"
    assert editor._flush_current_editor() is True
    assert editor.enum_data["Status"]["description"] == "same"


def test_update_meta_rejects_missing_empty_and_duplicate(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    errors = []
    monkeypatch.setattr(module.messagebox, "showerror",
                        lambda *args, **_kwargs: errors.append(args[1]))
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {
        "Status": {
            "name": "Status",
            "values": {}
        },
        "Other": {
            "name": "Other",
            "values": {}
        },
    }
    editor.name_entry = _ValueWidget("")
    editor.description_text = _ValueWidget()
    editor.enum_tree = _TreeStub()
    editor.value_tree = _TreeStub()

    editor.current_enum_key = None
    assert editor._update_enum_meta() is False
    editor.current_enum_key = "Missing"
    assert editor._update_enum_meta() is False
    editor.current_enum_key = "Status"
    assert editor._update_enum_meta() is False
    editor.name_entry.value = "Other"
    assert editor._update_enum_meta() is False
    assert errors == [
        "Enum name cannot be empty.", "Enum name 'Other' already exists."
    ]


def test_add_and_remove_enum_guard_branches(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    errors = []
    monkeypatch.setattr(module.messagebox, "showerror",
                        lambda *args, **_kwargs: errors.append(args))
    editor = object.__new__(module.EnumDefDictEditor)
    editor.enum_data = {"Enum1": {"name": "Enum1", "values": {}}}
    editor.enum_tree = _TreeStub()
    editor.start_value_entry = _ValueWidget("bad")
    editor._flush_current_editor = lambda: False

    editor._add_enum()
    assert list(editor.enum_data) == ["Enum1"]

    editor._flush_current_editor = lambda: True
    editor._add_enum()
    assert list(editor.enum_data) == ["Enum1"]
    assert errors[-1][0] == "Add Enum Error"

    editor._remove_enum()
    editor.enum_tree.selected = ["Missing"]
    editor._remove_enum()
    assert list(editor.enum_data) == ["Enum1"]


def test_add_and_insert_value_number_errors(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    errors = []
    monkeypatch.setattr(module.messagebox, "showerror",
                        lambda *args, **_kwargs: errors.append(args[0]))
    editor = object.__new__(module.EnumDefDictEditor)
    editor.current_enum_key = "Status"
    editor.start_value_entry = _ValueWidget("5")
    editor.value_tree = _TreeStub({"value-1": ("ONE", "bad")})

    editor._add_value()
    editor.value_tree.selected = ["value-1"]
    editor._insert_value()
    assert editor.value_tree.rows["value-2"] == ("VALUE_2", "5")

    editor.value_tree = _TreeStub(
        {
            "value-1": ("ONE", "bad"),
            "value-2": ("TWO", "2"),
        },
        selected=("value-2", ))
    editor._insert_value()
    assert errors == ["Add Value Error", "Insert Value Error"]


def test_shift_cancel_and_remove_without_selection(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    editor = object.__new__(module.EnumDefDictEditor)
    editor.value_tree = _TreeStub({"value-1": ("ONE", "1")},
                                  selected=("value-1", ))
    editor._ask_value_shift = lambda: None

    editor._shift_selected_values()
    assert editor.value_tree.rows["value-1"] == ("ONE", "1")

    editor.value_tree.selected = []
    editor._remove_value()
    assert "value-1" in editor.value_tree.rows


def test_value_shift_dialog_rejects_negative_amount(monkeypatch):
    module = _load_enum_editor_module(monkeypatch)
    buttons = []
    errors = []
    entry = _UiWidget()

    class StringVar:

        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    def button_factory(*args, **kwargs):
        widget = _UiWidget(*args, **kwargs)
        buttons.append(widget)
        return widget

    monkeypatch.setattr(module.tk, "Toplevel", _UiWidget)
    monkeypatch.setattr(module.tk, "StringVar", StringVar)
    monkeypatch.setattr(module.ttk, "Label", _UiWidget)
    monkeypatch.setattr(module.ttk, "Combobox", _UiWidget)
    monkeypatch.setattr(module.ttk, "Button", button_factory)
    monkeypatch.setattr(module, "EntryEx", lambda *_args, **_kwargs: entry)
    monkeypatch.setattr(module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))

    def show_modal(_parent, dialog):
        entry.value = "-1"
        apply = next(button for button in buttons
                     if button.options["text"] == "Apply")
        apply.options["command"]()
        assert dialog.destroyed is False

    monkeypatch.setattr(module, "show_modal_window", show_modal)
    editor = object.__new__(module.EnumDefDictEditor)

    assert editor._ask_value_shift() is None
    assert errors[0][0][:2] == ("Invalid Shift",
                                "Shift value must be non-negative.")
