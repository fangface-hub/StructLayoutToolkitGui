"""Tests for the EnumDefDictEditor class."""
# pylint: disable=duplicate-code,protected-access
import importlib
import sys
import types


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
