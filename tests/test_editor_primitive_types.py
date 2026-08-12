"""Tests for the StructDefDictEditor class."""
import importlib
import json
import sys
import types

import pytest

# pylint: disable=protected-access


def _install_sltcodec(monkeypatch, *, primitive_types=None, **extra):
    """Install a monkeypatched version of the sltcodec module.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    primitive_types : set[str], optional
        The set of primitive types to use in the monkeypatched module.
    **extra : dict
        Additional attributes to set on the monkeypatched module.
    """

    sltcodec_module = types.ModuleType("sltcodec")
    sltcodec_module.__path__ = []
    sltcodec_module.PRIMITIVE_TYPES = set(primitive_types or {"int16", "uint8"})
    sltcodec_module.FieldDef = object
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
    sltcodec_module.EnumDef = object
    for key, value in extra.items():
        setattr(sltcodec_module, key, value)

    monkeypatch.setitem(sys.modules, "sltcodec", sltcodec_module)
    return sltcodec_module


def _install_core(monkeypatch, *, info_size_cls=object):
    """Install a monkeypatched version of the sltcore module.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    info_size_cls : type, optional
        The class to use for the InfoSize attribute in the monkeypatched module.
    """
    sltcore_module = types.ModuleType("sltcore")
    sltcore_module.InfoSize = info_size_cls
    sltcore_module.bits_get = object
    monkeypatch.setitem(sys.modules, "sltcore", sltcore_module)
    return sltcore_module


def _install_gui_stubs(monkeypatch):
    """Install monkeypatched versions of the tkinterex and treeviewex modules.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    tkinterex_module = types.ModuleType("tkinterex")
    tkinterex_module.EntryEx = object
    tkinterex_module.ComboboxEx = object
    tkinterex_module.SelectDialog = object
    tkinterex_module.TextEx = object
    tkinterex_module.show_modal_window = lambda parent, modal_window: None

    treeviewex_module = types.ModuleType("treeviewex")
    treeviewex_module.TreeviewEx = object

    monkeypatch.setitem(sys.modules, "tkinterex", tkinterex_module)
    monkeypatch.setitem(sys.modules, "treeviewex", treeviewex_module)


class _ValueWidget:
    """Minimal value-bearing editor widget."""

    def __init__(self, value=""):
        self.value = value
        self.configured = []

    def configure(self, **kwargs):
        self.configured.append(kwargs)


class _TreeStub:
    """In-memory Treeview subset used by controller tests."""

    def __init__(self, rows=()):
        self.rows = {row_id: tuple(values) for row_id, values in rows}
        self.order = list(self.rows)
        self.selected = []
        self.calls = []

    def get_children(self):
        return tuple(self.order)

    def insert(self, _parent, index, iid, values):
        self.rows[iid] = tuple(values)
        if index == "end":
            self.order.append(iid)
        else:
            self.order.insert(index, iid)

    def delete(self, *row_ids):
        for row_id in row_ids:
            self.rows.pop(row_id, None)
            if row_id in self.order:
                self.order.remove(row_id)

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
        self.calls.append(("selection_set", row_id))

    def focus(self, row_id):
        self.calls.append(("focus", row_id))

    def see(self, row_id):
        self.calls.append(("see", row_id))

    def set_combobox_column(self, column_id, values=None, _is_combobox=True):
        self.calls.append(("combobox", column_id, list(values or [])))


class _UiWidget:
    """Recorder for ttk widgets used while building an editor."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.value = ""
        self.calls = []
        type(self).instances.append(self)

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def pack(self, **kwargs):
        return self._record("pack", **kwargs)

    def grid(self, **kwargs):
        return self._record("grid", **kwargs)

    def add(self, *args, **kwargs):
        return self._record("add", *args, **kwargs)

    def configure(self, *args, **kwargs):
        return self._record("configure", *args, **kwargs)

    def columnconfigure(self, *args, **kwargs):
        return self._record("columnconfigure", *args, **kwargs)

    def bind(self, *args, **kwargs):
        return self._record("bind", *args, **kwargs)

    def focus_set(self):
        return self._record("focus_set")


class _UiTree(_TreeStub):
    """Tree controller stub that also records UI configuration."""

    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.args = args
        self.kwargs = kwargs
        type(self).instances.append(self)

    def heading(self, *args, **kwargs):
        self.calls.append(("heading", args, kwargs))

    def column(self, *args, **kwargs):
        self.calls.append(("column", args, kwargs))

    def set_readonly_column(self, column_id):
        self.calls.append(("readonly", column_id))

    def pack(self, **kwargs):
        self.calls.append(("pack", kwargs))

    def bind(self, *args, **kwargs):
        self.calls.append(("bind", args, kwargs))


def _load_struct_editor_controller(monkeypatch):
    """Load the editor with deterministic codec and InfoSize stubs."""

    class DummyInfoSize:

        def __init__(self, byte=0, bit=0):
            self.byte = byte + (bit >> 3)
            self.bit = bit & 7

        def __add__(self, other):
            return type(self)(self.byte + other.byte, self.bit + other.bit)

        def __sub__(self, other):
            total_bits = (self.byte * 8 + self.bit - other.byte * 8 - other.bit)
            if total_bits < 0:
                raise ValueError("InfoSize cannot be negative")
            return type(self)(0, total_bits)

        def serialize(self):
            return json.dumps({
                "__type__": "InfoSize",
                "byte": self.byte,
                "bit": self.bit,
            })

    class DummyFieldDef:

        def __init__(self, value):
            self.value = value

        @classmethod
        def from_dict(cls, value):
            return cls(value)

        def to_dict(self):
            return self.value.copy()

    class DummyStructDef(DummyFieldDef):
        pass

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"uint8", "unsigned int"},
        FieldDef=DummyFieldDef,
        StructDef=DummyStructDef,
    )
    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)
    return importlib.import_module("sltgui.struct_def_dict_editor")


def test_editor_uses_public_primitive_types(monkeypatch):
    """Test that the StructDefDictEditor uses the public PRIMITIVE_TYPES
       from sltcodec.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    _install_gui_stubs(monkeypatch)
    sltcodec_module = _install_sltcodec(
        monkeypatch,
        primitive_types={"int16", "uint8"},
    )
    _install_core(monkeypatch, info_size_cls=object)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")

    expected = tuple(sorted(sltcodec_module.PRIMITIVE_TYPES))
    assert editor_module.PRIMITIVE_TYPES == expected


def test_type_column_uses_treeview_numeric_id(monkeypatch):
    """Test that the type column uses the correct numeric ID in the Treeview.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    _install_gui_stubs(monkeypatch)
    _install_sltcodec(monkeypatch, primitive_types={"int16", "uint8"})
    _install_core(monkeypatch, info_size_cls=object)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")

    seen = []

    class DummyTree:
        """A dummy treeview that records calls to set_combobox_column."""

        def set_combobox_column(
            self,
            column_id,
            values=None,
            _is_combobox=True,
        ):
            """Record the column ID and values passed to set_combobox_column.
            Parameters
            ----------
            column_id : str
                The ID of the column being set.
            values : list, optional
                The list of values for the combobox column.
            _is_combobox : bool, optional
                Indicates if the column is a combobox.
            """
            seen.append((column_id, values))

    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.field_tree = DummyTree()
    editor.struct_data = {}
    getattr(editor, "_refresh_type_combobox_values")()

    assert seen == [("#4", list(editor_module.PRIMITIVE_TYPES))]


def test_infosize_cells_support_static_values_and_expressions(monkeypatch):
    """Test that InfoSize cells support both static values and expressions.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """
    _install_gui_stubs(monkeypatch)
    _install_sltcodec(monkeypatch, primitive_types={"int16", "uint8"})

    class DummyInfoSize:
        """A dummy InfoSize class that supports serialization
           and deserialization."""

        def __init__(self, byte, bit):
            """Initialize the DummyInfoSize with byte and bit values.
            Parameters
            ----------
            byte : int
                The byte component of the InfoSize.
            bit : int
                The bit component of the InfoSize.
            """
            self.byte = byte + (bit >> 3)
            self.bit = bit & 7

        def serialize(self):
            """Serialize the DummyInfoSize to a JSON string."""
            return '{"__type__":"InfoSize","byte":%d,"bit":%d}' % (
                self.byte,
                self.bit,
            )

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    editor_cls = editor_module.StructDefDictEditor

    infosize_to_string = getattr(editor_cls, "_infosize_value_to_string")
    parse_infosize = getattr(editor_cls, "_parse_infosize_input")

    assert infosize_to_string({
        "__type__": "InfoSize",
        "byte": 2,
        "bit": 9,
    }) == "3,1"
    assert infosize_to_string(DummyInfoSize(4, 0)) == "4,0"
    assert infosize_to_string("field_a.size * 2") == "field_a.size * 2"
    parsed_infosize = parse_infosize("3,1")
    assert isinstance(parsed_infosize, DummyInfoSize)
    assert (parsed_infosize.byte, parsed_infosize.bit) == (3, 1)
    assert parse_infosize("field_a.size * 2") == "field_a.size * 2"
    assert parse_infosize("InfoSize(1,0) * captured_packet_length") == (
        "InfoSize(1,0) * captured_packet_length")


def test_add_field_uses_next_offset_and_default_values(monkeypatch):
    """Test that Add Field appends a correctly positioned int field."""
    _install_gui_stubs(monkeypatch)
    _install_sltcodec(monkeypatch, primitive_types={"uint8"})

    class DummyInfoSize:
        """A dummy InfoSize class for Add Field calculations."""

        def __init__(self, byte=0, bit=0):
            self.byte = byte
            self.bit = bit

        def __add__(self, other):
            return DummyInfoSize(self.byte + other.byte, self.bit + other.bit)

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)
    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")

    class DummyFieldTree:
        """A minimal tree stub for Add Field."""

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

    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.current_struct_key = "Packet"
    editor.field_tree = DummyFieldTree()
    editor._add_field()
    editor._add_field()
    editor.field_tree.selected = ["field-2"]

    requested = []

    def fake_ask_infosize_dialog(
        _title,
        *,
        include_sign,
        initial_amount,
    ):
        requested.append((include_sign, initial_amount))
        return None

    editor._ask_infosize_dialog = fake_ask_infosize_dialog
    editor._ask_offset_shift()
    assert requested[0][0] is True
    assert (requested[0][1].byte, requested[0][1].bit) == (4, 0)

    editor._initial_field_size = DummyInfoSize(8, 0)
    editor._initial_field_type = "uint8"
    editor._insert_field()

    assert editor.field_tree.rows[0][1][1:] == (
        "0,0",
        "4,0",
        "unsigned int",
        "1.0",
        "",
        "",
        "",
        "",
        "false",
    )
    assert editor.field_tree.rows[1][1][1:] == (
        "4,0",
        "8,0",
        "uint8",
        "1.0",
        "",
        "",
        "",
        "",
        "false",
    )
    assert editor.field_tree.rows[2][1][1:] == (
        "4,0",
        "4,0",
        "unsigned int",
        "1.0",
        "",
        "",
        "",
        "",
        "false",
    )


def test_field_enum_def_name_round_trips_through_treeview(monkeypatch):
    """Test that the enum_def_name field round-trips through the Treeview.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """

    class DummyFieldDef:
        """A dummy FieldDef class that supports serialization
           and deserialization."""

        def __init__(self, field_dict):
            """Initialize the DummyFieldDef with a field dictionary.

            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.
            """
            self.field_dict = field_dict

        @classmethod
        def from_dict(cls, field_dict):
            """Create a DummyFieldDef instance from a field dictionary.

            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.

            Returns
            -------
            DummyFieldDef
                A new DummyFieldDef instance initialized
                with the field dictionary.
            """
            return cls(field_dict)

        def to_dict(self):
            """Convert the DummyFieldDef instance to a field dictionary.

            Returns
            -------
            dict
                A copy of the field dictionary representing
                the DummyFieldDef instance.
            """
            return self.field_dict.copy()

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"bool"},
        FieldDef=DummyFieldDef,
    )

    class DummyInfoSize:
        """A dummy InfoSize class that supports serialization
           and deserialization."""

        def __init__(self, byte, bit):
            """Initialize the DummyInfoSize with byte and bit components.

            Parameters
            ----------
            byte : int
                The byte component of the InfoSize.
            bit : int
                The bit component of the InfoSize.
            """
            self.byte = byte
            self.bit = bit

        def serialize(self):
            """Serialize the DummyInfoSize to a JSON string."""
            return '{"__type__":"InfoSize","byte":%d,"bit":%d}' % (
                self.byte,
                self.bit,
            )

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {"Status": {"__type__": "EnumDef", "name": "Status"}}

    row_map = {
        "name": "status",
        "offset": "0,0",
        "size": "1,0",
        "type": "bool",
        "scale": "1.0",
        "repeat": "",
        "description": "",
        "range_expression": "",
        "enum_def_name": "Status",
        "byte_swap": "false",
    }
    field_dict = editor._row_map_to_field_dict(row_map)
    assert field_dict["enum_def_name"] == "Status"
    values = editor._field_data_to_row_values({"enum_def_name": "Status"})
    assert values[-2] == "Status"


def test_field_byte_swap_round_trips_through_treeview(monkeypatch):
    """Test that the byte_swap field round-trips through the Treeview.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying sys.modules.
    """

    class DummyFieldDef:
        """A dummy FieldDef class that supports serialization
           and deserialization."""

        def __init__(self, field_dict):
            """Initialize the DummyFieldDef with a field dictionary.

            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.
            """
            self.field_dict = field_dict

        @classmethod
        def from_dict(cls, field_dict):
            """Create a DummyFieldDef instance from a field dictionary.
            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.
            Returns
            -------
            DummyFieldDef
                A new DummyFieldDef instance initialized
                with the field dictionary.
            """
            return cls(field_dict)

        def to_dict(self):
            """Convert the DummyFieldDef instance to a field dictionary."""
            return self.field_dict.copy()

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"bool"},
        FieldDef=DummyFieldDef,
    )

    class DummyInfoSize:
        """A dummy InfoSize class that supports serialization
           and deserialization."""

        def __init__(self, byte, bit):
            """Initialize the DummyInfoSize with byte and bit values.

            Parameters
            ----------
            byte : int
                The byte value.
            bit : int
                The bit value.
            """
            self.byte = byte
            self.bit = bit

        def serialize(self):
            """Serialize the DummyInfoSize to a JSON string."""
            return '{"__type__":"InfoSize","byte":%d,"bit":%d}' % (
                self.byte,
                self.bit,
            )

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {}

    row_map = {
        "name": "data",
        "offset": "0,0",
        "size": "2,0",
        "type": "u16",
        "scale": "1.0",
        "repeat": "",
        "description": "",
        "range_expression": "",
        "enum_def_name": "",
        "byte_swap": "true",
    }
    field_dict = editor._row_map_to_field_dict(row_map)
    assert field_dict["byte_swap"] is True
    assert "byte_swap" in editor_module.FIELD_COLUMNS
    assert editor._field_data_to_row_values(field_dict)[-1] == "true"

    row_map["byte_swap"] = "header_length % 2 == 0"
    field_dict = editor._row_map_to_field_dict(row_map)
    assert field_dict["byte_swap"] == "header_length % 2 == 0"
    assert editor._field_data_to_row_values(field_dict)[-1] == (
        "header_length % 2 == 0")


def test_field_repeat_accepts_expression(monkeypatch):
    """Test that repeat expressions are passed through to sltcodec."""

    class DummyFieldDef:
        """A dummy FieldDef class that records the input dictionary."""

        def __init__(self, field_dict):
            self.field_dict = field_dict

        @classmethod
        def from_dict(cls, field_dict):
            return cls(field_dict)

        def to_dict(self):
            return self.field_dict.copy()

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"uint8"},
        FieldDef=DummyFieldDef,
    )

    class DummyInfoSize:
        """A dummy InfoSize class for parsing static cell values."""

        def __init__(self, byte, bit):
            self.byte = byte
            self.bit = bit

        def serialize(self):
            return '{"__type__":"InfoSize","byte":%d,"bit":%d}' % (
                self.byte,
                self.bit,
            )

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {}

    field_dict = editor._row_map_to_field_dict({
        "name": "data",
        "offset": "0,0",
        "size": "1,0",
        "type": "uint8",
        "scale": "1.0",
        "repeat": "packet_length - header_length",
        "description": "",
        "range_expression": "",
        "enum_def_name": "",
        "byte_swap": "false",
    })

    assert field_dict["repeat"] == "packet_length - header_length"


def test_field_infosizes_remain_typed_json_after_normalization(monkeypatch):
    """Test that InfoSize fields remain typed JSON after normalization.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The monkeypatch fixture for modifying module attributes during the test.
    """

    class DummyFieldDef:
        """A dummy FieldDef class that supports serialization
           and deserialization."""

        def __init__(self, field_dict):
            """Initialize the DummyFieldDef with a field dictionary.

            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.
            """
            self.field_dict = field_dict

        @classmethod
        def from_dict(cls, field_dict):
            """Create a DummyFieldDef instance from a field dictionary.
            Parameters
            ----------
            field_dict : dict
                The dictionary representing the field definition.

            Returns
            -------
            DummyFieldDef
                A new DummyFieldDef instance initialized
                with the field dictionary.
            """
            return cls(field_dict)

        def to_dict(self):
            """Convert the DummyFieldDef instance to a field dictionary.

            Returns
            -------
            dict
                The dictionary representing the field definition.
            """
            normalized = self.field_dict.copy()
            normalized["offset"] = json.dumps(normalized["offset"])
            normalized["size"] = json.dumps(normalized["size"])
            return normalized

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"bool"},
        FieldDef=DummyFieldDef,
    )

    class DummyInfoSize:
        """A dummy InfoSize class that supports serialization
           and deserialization."""

        def __init__(self, byte, bit):
            """Initialize the DummyInfoSize with byte and bit values.

            Parameters
            ----------
            byte : int
                The byte component of the InfoSize.
            bit : int
                The bit component of the InfoSize.
            """
            self.byte = byte + (bit >> 3)
            self.bit = bit & 7

        def serialize(self):
            """Serialize the DummyInfoSize to a JSON string."""
            return '{"__type__":"InfoSize","byte":%d,"bit":%d}' % (
                self.byte,
                self.bit,
            )

    _install_core(monkeypatch, info_size_cls=DummyInfoSize)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {}

    field_dict = editor._row_map_to_field_dict({
        "name": "field_1",
        "offset": "0,0",
        "size": "1,0",
        "type": "bool",
        "scale": "1.0",
        "repeat": "",
        "description": "",
        "range_expression": "",
        "enum_def_name": "",
    })

    assert isinstance(field_dict["offset"], DummyInfoSize)
    assert (field_dict["offset"].byte, field_dict["offset"].bit) == (0, 0)
    assert isinstance(field_dict["size"], DummyInfoSize)
    assert (field_dict["size"].byte, field_dict["size"].bit) == (1, 0)

    json_data = editor._struct_data_to_json_data({
        "Struct1": {
            "name":
            "Struct1",
            "description":
            "",
            "fields": [{
                **field_dict,
                "offset": field_dict["offset"].serialize(),
                "size": field_dict["size"].serialize(),
            }],
        },
    })

    assert json_data["Struct1"]["fields"][0]["offset"] == {
        "__type__": "InfoSize",
        "byte": 0,
        "bit": 0,
    }
    assert json_data["Struct1"]["fields"][0]["size"] == {
        "__type__": "InfoSize",
        "byte": 1,
        "bit": 0,
    }


def test_enum_def_cells_preserve_typed_json(monkeypatch):
    """Test that EnumDef cells preserve typed JSON in the editor.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The monkeypatch fixture for modifying modules
        and attributes during testing.
    """
    _install_gui_stubs(monkeypatch)
    _install_sltcodec(monkeypatch, primitive_types={"int16", "uint8"})
    _install_core(monkeypatch, info_size_cls=object)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    enum_def = {
        "name": "Status",
        "description": "Current status",
        "values": {
            "READY": 1,
            "DONE": 2,
        },
    }

    parse_enum_def = getattr(
        editor_module.StructDefDictEditor,
        "_parse_enum_def_input",
    )
    parsed = parse_enum_def(json.dumps(enum_def))

    assert parsed == "Status"


def test_enum_def_field_uses_loaded_enum_names(monkeypatch):
    """Test that the enum_def_name field uses loaded enum names in the editor.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The monkeypatch fixture for modifying modules
        and attributes during testing.
    """
    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"int16", "uint8"},
        EnumDef=object,
    )
    _install_core(monkeypatch, info_size_cls=object)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)

    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")

    class DummyTree:
        """A dummy treeview that records calls to set_combobox_column."""

        def __init__(self):
            """Initialize the DummyTree with an empty list
               to record seen calls."""
            self.seen = []

        def set_combobox_column(self,
                                column_id,
                                values=None,
                                _is_combobox=True):
            """Record the column ID and values passed to set_combobox_column.
            Parameters
            ----------
            column_id : str
                The ID of the column being set.
            values : list, optional
                The list of values for the combobox column.
            _is_combobox : bool, optional
                Flag indicating if the column is a combobox.
            """
            self.seen.append((column_id, list(values)))

    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.field_tree = DummyTree()
    editor.enum_def_dict = {
        "Status": {
            "__type__": "EnumDef",
            "name": "Status",
            "description": "",
            "values": {
                "READY": 1,
            },
        }
    }
    editor._refresh_enum_combobox_values()

    assert editor.field_tree.seen == [("#9", ["Status"])]
    assert editor._parse_enum_def_input("Status") == "Status"


def test_struct_editor_update_preserves_enum_definitions(monkeypatch):
    """Test that updating structs preserves enum definitions.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The monkeypatch fixture for modifying modules
        and attributes during testing.
    """

    class DummyStructDef:
        """A dummy StructDef class that supports serialization
           and deserialization."""

        @classmethod
        def from_dict(cls, _value):
            """Create a DummyStructDef instance from a dictionary.
            Parameters
            ----------
            _value : dict
                The dictionary representation of the DummyStructDef.

            Returns
            -------
            DummyStructDef
                The created DummyStructDef instance.
            """
            return object()

    _install_gui_stubs(monkeypatch)
    _install_sltcodec(
        monkeypatch,
        primitive_types={"int16", "uint8"},
        StructDef=DummyStructDef,
    )
    _install_core(monkeypatch, info_size_cls=object)
    sys.modules.pop("sltgui.struct_def_dict_editor", None)
    editor_module = importlib.import_module("sltgui.struct_def_dict_editor")
    enum_def = object()
    destroyed = []
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.type_dict = types.SimpleNamespace(
        enum_dict={"Status": enum_def},
        struct_dict={},
    )
    editor.struct_data = {}
    editor._flush_current_editor = lambda: True
    editor.destroy = lambda: destroyed.append(True)

    editor._on_update()

    assert destroyed == [True]
    assert editor.type_dict.enum_dict["Status"] is enum_def


def test_struct_tree_loading_selection_and_clearing(monkeypatch):
    """Exercise struct tree refresh, selection, loading, and clearing."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.struct_tree = _TreeStub([("stale", ("stale", ))])
    editor.field_tree = _TreeStub([("old-field", ("old", ))])
    editor.name_entry = _ValueWidget("old")
    editor.description_text = _ValueWidget("old description")
    editor.enum_def_dict = {"Status": {"name": "Status"}}
    editor.struct_data = {
        "Packet": {
            "name":
            "Packet",
            "description":
            "packet data",
            "fields": [{
                "name": "length",
                "offset": "0,0",
                "size": "1,0",
                "type": "uint8",
            }],
        },
    }
    editor.current_struct_key = None

    editor._refresh_struct_tree()
    assert editor.struct_tree.order == ["Packet"]
    editor._select_struct("missing")
    assert editor.current_struct_key is None

    editor._select_struct("Packet")
    assert editor.current_struct_key == "Packet"
    assert editor.name_entry.value == "Packet"
    assert editor.description_text.value == "packet data"
    assert editor.field_tree.order == ["field-1"]

    editor._load_struct_to_editor("missing")
    assert editor.current_struct_key is None
    assert editor.name_entry.value == ""
    assert editor.field_tree.order == []

    loaded = []
    editor._load_struct_to_editor = loaded.append
    editor.current_struct_key = "Packet"
    editor.struct_tree.selected = []
    editor._on_struct_selected(None)
    editor.struct_tree.selected = ["Packet"]
    editor._on_struct_selected(None)
    editor.struct_tree.selected = ["Other"]
    editor._flush_current_editor = lambda: False
    editor._on_struct_selected(None)
    editor._flush_current_editor = lambda: True
    editor._on_struct_selected(None)
    assert loaded == ["Other"]


def test_flush_current_editor_validates_and_renames(monkeypatch):
    """Validate flush failures and successful struct renaming."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    errors = []
    monkeypatch.setattr(
        editor_module.messagebox,
        "showerror",
        lambda *args, **kwargs: errors.append((args, kwargs)),
    )
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.name_entry = _ValueWidget("")
    editor.description_text = _ValueWidget("updated")
    editor.field_tree = _TreeStub()
    editor.struct_tree = _TreeStub()
    editor.struct_data = {"Packet": {"name": "Packet"}, "Other": {}}
    editor.current_struct_key = None
    assert editor._flush_current_editor() is True

    editor.current_struct_key = "missing"
    assert editor._flush_current_editor() is True
    assert editor.current_struct_key is None

    editor.current_struct_key = "Packet"
    assert editor._flush_current_editor() is False
    editor.name_entry.value = "Other"
    assert editor._flush_current_editor() is False

    editor.name_entry.value = "Renamed"
    editor.field_tree = _TreeStub([("field-1", (
        "length",
        "0,0",
        "1,0",
        "uint8",
        "1",
        "",
        "",
        "",
        "",
        "false",
    ))])
    editor._select_struct = lambda key: editor.struct_tree.calls.append(
        ("select", key))
    assert editor._flush_current_editor() is True
    assert "Packet" not in editor.struct_data
    assert editor.struct_data["Renamed"]["fields"][0]["name"] == "length"
    assert editor.current_struct_key == "Renamed"
    assert len(errors) == 2

    editor.current_struct_key = "Renamed"
    editor.name_entry.value = "Renamed"
    assert editor._flush_current_editor() is True
    assert editor.struct_tree.rows["Renamed"] == ("Renamed", )


def test_struct_meta_add_and_remove_actions(monkeypatch):
    """Exercise metadata validation and struct collection actions."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.name_entry = _ValueWidget("")
    editor.description_text = _ValueWidget("description")
    editor.struct_tree = _TreeStub()
    editor.field_tree = _TreeStub()
    editor.struct_data = {"Struct1": {"name": "Struct1", "fields": []}}
    editor.current_struct_key = None
    assert editor._update_struct_meta() is False
    editor.current_struct_key = "missing"
    assert editor._update_struct_meta() is False
    editor.current_struct_key = "Struct1"
    assert editor._update_struct_meta() is False

    editor.struct_data["Taken"] = {"name": "Taken", "fields": []}
    editor.name_entry.value = "Taken"
    assert editor._update_struct_meta() is False
    editor.name_entry.value = "Packet"
    assert editor._update_struct_meta() is True
    assert editor.struct_data["Packet"]["description"] == "description"
    assert editor.struct_tree.selected == ["Packet"]

    editor._flush_current_editor = lambda: False
    editor._add_struct()
    assert "Struct1" not in editor.struct_data
    editor._flush_current_editor = lambda: True
    editor._select_struct = lambda key: editor.struct_tree.calls.append(
        ("select", key))
    editor._add_struct()
    assert "Struct1" in editor.struct_data
    editor._add_struct()
    assert "Struct2" in editor.struct_data

    editor.struct_tree.selected = []
    editor._remove_struct()
    editor.struct_tree.selected = ["missing"]
    editor._remove_struct()
    editor.struct_tree.selected = ["Struct1"]
    editor._remove_struct()
    assert "Struct1" not in editor.struct_data
    assert ("select", "Taken") in editor.struct_tree.calls
    assert len(errors) == 2

    editor.struct_data = {"Only": {"name": "Only", "fields": []}}
    editor.struct_tree = _TreeStub([("Only", ("Only", ))])
    editor.struct_tree.selected = ["Only"]
    cleared = []
    editor._clear_editor = lambda: cleared.append(True)
    editor._remove_struct()
    assert cleared == [True]


def test_field_bulk_actions_and_error_paths(monkeypatch):
    """Exercise field removal, offset shifting, and multi-row sizing."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    info_size = editor_module.InfoSize
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    rows = [
        ("field-1", ("a", "1,0", "1,0", "uint8", "1", "", "", "", "", "false")),
        ("field-2", ("b", "3,0", "1,0", "uint8", "1", "", "", "", "", "false")),
    ]
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.field_tree = _TreeStub(rows)

    editor._shift_selected_offsets()
    editor._update_selected_sizes()
    assert len(errors) == 2

    editor.field_tree.selected = ["field-1", "field-2"]
    editor._ask_offset_shift = lambda: None
    editor._shift_selected_offsets()
    editor._ask_offset_shift = lambda: editor_module._OffsetShift(
        "+", info_size(0, 4))
    editor._shift_selected_offsets()
    assert editor.field_tree.rows["field-1"][1] == "1,4"
    assert editor.field_tree.rows["field-2"][1] == "3,4"

    editor._ask_offset_shift = lambda: editor_module._OffsetShift(
        "-", info_size(0, 4))
    editor._shift_selected_offsets()
    assert editor.field_tree.rows["field-1"][1] == "1,0"

    editor._ask_infosize_dialog = lambda *args, **kwargs: None
    editor._update_selected_sizes()
    editor._ask_infosize_dialog = lambda *args, **kwargs: (
        editor_module._OffsetShift("+", info_size(2, 3)))
    editor._update_selected_sizes()
    assert editor.field_tree.rows["field-1"][2] == "2,3"
    assert editor.field_tree.rows["field-2"][2] == "2,3"

    editor._remove_field()
    assert editor.field_tree.order == []
    editor.field_tree.selected = []
    editor._remove_field()


def test_initial_field_controls_and_add_insert_errors(monkeypatch):
    """Cover default field controls and add/insert validation errors."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    info_size = editor_module.InfoSize
    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.field_tree = _TreeStub([("field-1", (
        "a",
        "expression",
        "1,0",
        "uint8",
        "1",
        "",
        "",
        "",
        "",
        "false",
    ))])
    editor.current_struct_key = None
    editor._add_field()
    editor._insert_field()

    editor.current_struct_key = "Packet"
    editor._add_field()
    editor.field_tree.selected = []
    editor._insert_field()
    editor.field_tree.selected = ["field-1"]
    editor._insert_field()

    editor.field_tree = _TreeStub([
        ("field-1", ("a", "bad", "1,0")),
        ("field-2", ("b", "1,0", "1,0")),
    ])
    editor.field_tree.selected = ["field-2"]
    editor._insert_field()

    editor._initial_field_size = info_size(4, 0)
    editor.initial_size_label = _ValueWidget()
    editor._ask_infosize_dialog = lambda *args, **kwargs: None
    editor._set_initial_field_size()
    editor._ask_infosize_dialog = lambda *args, **kwargs: (
        editor_module._OffsetShift("+", info_size(8, 1)))
    editor._set_initial_field_size()
    assert editor._format_initial_size() == "8,1"
    assert editor.initial_size_label.configured == [{"text": "8,1"}]

    editor.initial_type_combo = _ValueWidget("uint8")
    editor._on_initial_type_changed(None)
    assert editor._initial_field_type == "uint8"
    assert [error[0] for error in errors] == [
        "No Struct",
        "No Struct",
        "Add Field Error",
        "No Field Selected",
        "Insert Field Error",
    ]


def test_editor_constructor_builds_ui_and_empty_state(monkeypatch):
    """Build the complete editor with recorder widgets and no Tk display."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    _UiWidget.instances = []
    _UiTree.instances = []
    window_calls = []
    monkeypatch.setattr(editor_module.tk.Toplevel, "__init__",
                        lambda self, parent: setattr(self, "master", parent))
    for method_name in ("withdraw", "title", "geometry", "config",
                        "pack_propagate"):
        monkeypatch.setattr(
            editor_module.StructDefDictEditor,
            method_name,
            lambda self, *args, _name=method_name, **kwargs: window_calls.
            append((_name, args, kwargs)),
        )
    monkeypatch.setattr(editor_module.StructDefDictEditor, "winfo_screenwidth",
                        lambda self: 1920)
    monkeypatch.setattr(editor_module.StructDefDictEditor, "winfo_screenheight",
                        lambda self: 1080)
    monkeypatch.setattr(editor_module.ttk, "Panedwindow", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Frame", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "LabelFrame", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Label", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Button", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Style", _UiWidget)
    monkeypatch.setattr(editor_module, "EntryEx", _UiWidget)
    monkeypatch.setattr(editor_module, "TextEx", _UiWidget)
    monkeypatch.setattr(editor_module, "ComboboxEx", _UiWidget)
    monkeypatch.setattr(editor_module, "TreeviewEx", _UiTree)

    type_dict = types.SimpleNamespace(struct_dict={}, enum_dict={})
    editor = editor_module.StructDefDictEditor(object(), type_dict)

    assert editor.type_dict is type_dict
    assert editor.current_struct_key is None
    assert editor.name_entry.value == ""
    assert editor.description_text.value == ""
    assert len(_UiTree.instances) == 2
    assert ("geometry", ("1280x760", ), {}) in window_calls
    button_texts = {
        widget.kwargs["text"]
        for widget in _UiWidget.instances if "command" in widget.kwargs
    }
    assert {
        "Add Struct", "Remove Struct", "Add Field", "Insert Field",
        "Remove Field", "Shift Offset", "Update Multi-line Size",
        "Initial Size", "Update", "Cancel"
    } <= button_texts

    destroyed = []
    editor.destroy = lambda: destroyed.append(True)
    editor._on_cancel()
    editor._flush_current_editor = lambda: False
    editor._on_update()
    assert destroyed == [True]


def test_heading_tooltip_schedules_shows_and_hides(monkeypatch):
    """Exercise tooltip region checks, scheduling, display, and cleanup."""
    editor_module = _load_struct_editor_controller(monkeypatch)

    class TooltipWidget:

        def __init__(self):
            self.region = "cell"
            self.column_id = "#2"
            self.callback = None
            self.cancelled = []
            self.bindings = []

        def bind(self, *args, **kwargs):
            self.bindings.append((args, kwargs))

        def identify_region(self, _x, _y):
            return self.region

        def identify_column(self, _x):
            return self.column_id

        def after(self, delay, callback):
            assert delay == 500
            self.callback = callback
            return "after-1"

        def after_cancel(self, after_id):
            self.cancelled.append(after_id)

    class TooltipWindow:

        def __init__(self, parent):
            self.parent = parent
            self.calls = []

        def wm_overrideredirect(self, value):
            self.calls.append(("override", value))

        def wm_geometry(self, value):
            self.calls.append(("geometry", value))

        def destroy(self):
            self.calls.append(("destroy", ))

    labels = []
    monkeypatch.setattr(editor_module.tk, "Toplevel", TooltipWindow)
    monkeypatch.setattr(
        editor_module.ttk,
        "Label",
        lambda *args, **kwargs: labels.append(_UiWidget(*args, **kwargs)) or
        labels[-1],
    )
    widget = TooltipWidget()
    tooltip = editor_module._HeadingToolTip(widget, {"#2": "offset help"})
    event = types.SimpleNamespace(x=2, y=3, x_root=10, y_root=20)

    tooltip._on_motion(event)
    widget.region = "heading"
    widget.column_id = "#3"
    tooltip._on_motion(event)
    widget.column_id = "#2"
    tooltip._on_motion(event)
    assert tooltip.after_id == "after-1"
    widget.callback()
    assert tooltip.window.calls[:2] == [("override", True),
                                        ("geometry", "+22+32")]
    assert labels[0].kwargs["text"] == "offset help"
    tooltip._hide()
    assert tooltip.window is None

    tooltip.after_id = "after-2"
    tooltip._hide()
    assert widget.cancelled == ["after-2"]


def test_infosize_dialog_apply_cancel_and_validation(monkeypatch):
    """Drive the InfoSize dialog callbacks through recorder controls."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    info_size = editor_module.InfoSize
    buttons = []
    entries = []
    errors = []

    class Dialog(_UiWidget):

        def title(self, value):
            self.calls.append(("title", value))

        def resizable(self, *values):
            self.calls.append(("resizable", values))

        def destroy(self):
            self.calls.append(("destroy", ))

    class Entry(_UiWidget):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            entries.append(self)

    class StringVariable:

        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    def make_button(*args, **kwargs):
        button = _UiWidget(*args, **kwargs)
        buttons.append(button)
        return button

    monkeypatch.setattr(editor_module.tk, "Toplevel", Dialog)
    monkeypatch.setattr(editor_module.tk, "StringVar", StringVariable)
    monkeypatch.setattr(editor_module.ttk, "Label", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Combobox", _UiWidget)
    monkeypatch.setattr(editor_module.ttk, "Button", make_button)
    monkeypatch.setattr(editor_module, "EntryEx", Entry)
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))
    editor = object.__new__(editor_module.StructDefDictEditor)

    monkeypatch.setattr(
        editor_module,
        "show_modal_window",
        lambda _parent, _dialog: next(button for button in reversed(
            buttons) if button.kwargs["text"] == "Apply").kwargs["command"](),
    )
    result = editor._ask_infosize_dialog("Shift Offset",
                                         include_sign=True,
                                         initial_amount=info_size(2, 3))
    assert (result.sign, result.amount.byte, result.amount.bit) == ("+", 2, 3)
    assert entries[-2].value == "2"
    assert entries[-1].value == "3"

    def submit_invalid(_parent, _dialog):
        entries[-2].value = "-1"
        next(button for button in reversed(buttons)
             if button.kwargs["text"] == "Apply").kwargs["command"]()

    monkeypatch.setattr(editor_module, "show_modal_window", submit_invalid)
    assert editor._ask_infosize_dialog("Initial Size",
                                       include_sign=False) is None
    assert errors[-1][0][0] == "Invalid Shift"


def test_loaded_type_dict_and_struct_conversions(monkeypatch):
    """Load non-empty codec data and convert edited structs back."""
    editor_module = _load_struct_editor_controller(monkeypatch)

    class EnumDef:

        def to_dict(self):
            return {"name": "Status", "description": "", "values": {}}

    struct_def = editor_module.StructDef({
        "name":
        "Packet",
        "description":
        "packet",
        "fields": [{
            "name": "length",
            "offset": "0,0",
            "size": "1,0",
            "type": "uint8",
        }],
    })
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.type_dict = types.SimpleNamespace(
        struct_dict={"Packet": struct_def},
        enum_dict={"Status": EnumDef()},
    )
    editor.struct_tree = _TreeStub()
    editor.field_tree = _TreeStub()
    editor.name_entry = _ValueWidget()
    editor.description_text = _ValueWidget()
    editor.current_struct_key = None

    editor._load_type_dict_data()
    assert editor.current_struct_key == "Packet"
    assert editor.enum_def_dict["Status"]["__type__"] == "EnumDef"
    assert isinstance(editor.struct_data["Packet"]["fields"][0]["size"],
                      editor_module.InfoSize)
    converted = editor._to_struct_def_dict()
    assert isinstance(converted["Packet"], editor_module.StructDef)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ('{"value": 1}', {
            "value": 1
        }),
        ("[1, 2]", [1, 2]),
        ("{invalid", "{invalid"),
    ],
)
def test_parse_json_or_raw_variants(monkeypatch, text, expected):
    """Parse valid JSON containers while preserving invalid input."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    parse_value = editor_module.StructDefDictEditor._parse_json_or_raw
    assert parse_value(text) == expected


def test_field_and_enum_validation_errors(monkeypatch):
    """Reject invalid field cells and malformed enum definitions."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {}
    valid_row = {
        "name": "field",
        "offset": "0,0",
        "size": "1,0",
        "type": "uint8",
        "scale": "1.0",
        "repeat": "",
        "enum_def_name": "",
    }

    for update, message in [({
            "name": " "
    }, "Field name cannot be empty"), ({
            "scale": "large"
    }, "Invalid scale")]:
        with pytest.raises(ValueError, match=message):
            editor._row_map_to_field_dict({**valid_row, **update})

    editor._parse_infosize_input = lambda _value: (_ for _ in ()).throw(
        ValueError("invalid static size"))
    with pytest.raises(ValueError, match="Invalid InfoSize"):
        editor._row_map_to_field_dict(valid_row)

    parse_enum = editor._parse_enum_def_input
    assert parse_enum(None) is None
    for value, message in [
        ("not-json", "enum_def must be a JSON object"),
        ("[]", "enum_def must be a JSON object or enum name"),
        ('{"__type__":"Other","name":"Status"}', "enum_def must have __type__"),
        ('{"name":""}', "enum_def name cannot be empty")
    ]:
        with pytest.raises(ValueError, match=message):
            parse_enum(value)

    assert editor_module.StructDefDictEditor._parse_enum_def_input(
        "Status", {"Status": {
            "name": "Status"
        }}) == "Status"


def test_offset_conversion_and_bulk_operation_failures(monkeypatch):
    """Report unshiftable expressions without partially updating rows."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    editor_cls = editor_module.StructDefDictEditor
    converted = editor_cls._row_offset_to_infosize({
        "__type__": "InfoSize",
        "byte": 2,
        "bit": 3,
    })
    assert (converted.byte, converted.bit) == (2, 3)
    with pytest.raises(ValueError, match="cannot be shifted"):
        editor_cls._row_offset_to_infosize("field_a.size")

    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    editor = object.__new__(editor_cls)
    editor.field_tree = _TreeStub([
        ("field-1", ("a", "field_a.size", "1,0")),
        ("field-2", ("b", "2,0", "1,0")),
    ])
    editor.field_tree.selected = ["field-1", "field-2"]
    editor._ask_offset_shift = lambda: editor_module._OffsetShift(
        "+", editor_module.InfoSize(1, 0))
    editor._shift_selected_offsets()
    assert errors[-1][0] == "Shift Offset Error"
    assert editor.field_tree.rows["field-2"][1] == "2,0"

    editor.field_tree.selected = ["field-2"]
    editor.field_tree.rows["field-1"] = ("a", "bad", "1,0")
    editor._ask_offset_shift = types.MethodType(editor_cls._ask_offset_shift,
                                                editor)
    editor._ask_infosize_dialog = lambda *args, **kwargs: None
    assert editor._ask_offset_shift() is None
    assert errors[-1][0] == "Shift Offset Error"

    editor.field_tree = _TreeStub([("field-1", ("a", "0,0", "1,0"))])
    editor.field_tree.selected = ["field-1"]
    requested = []
    editor._ask_infosize_dialog = lambda *args, **kwargs: requested.append(
        kwargs["initial_amount"])
    assert editor._ask_offset_shift() is None
    assert (requested[0].byte, requested[0].bit) == (0, 0)


def test_expression_conversion_and_flush_validation_failure(monkeypatch):
    """Preserve InfoSize expressions and surface invalid edited rows."""
    editor_module = _load_struct_editor_controller(monkeypatch)
    expression = "field_a.size * 2"
    json_data = editor_module.StructDefDictEditor._struct_data_to_json_data({
        "Packet": {
            "fields": [{
                "offset": expression,
                "size": "1,0"
            }],
        },
    })
    assert json_data["Packet"]["fields"][0]["offset"] == expression

    editor = object.__new__(editor_module.StructDefDictEditor)
    editor.enum_def_dict = {}
    normalized = editor._row_map_to_field_dict({
        "name": "payload",
        "offset": expression,
        "size": "1,0",
        "type": "uint8",
        "scale": "1",
        "repeat": "",
    })
    assert normalized["offset"] == expression

    errors = []
    monkeypatch.setattr(editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append(args))
    editor.current_struct_key = "Packet"
    editor.struct_data = {"Packet": {}}
    editor.name_entry = _ValueWidget("Packet")
    editor.description_text = _ValueWidget()
    editor.field_tree = _TreeStub([("field-1", ("bad", ))])
    editor._row_map_to_field_dict = lambda _row: (_ for _ in ()).throw(
        ValueError("invalid row"))
    assert editor._flush_current_editor() is False
    assert errors == [("Validation Error", "invalid row")]

    original_parser = editor_module.StructDefDictEditor._parse_infosize_input
    editor_module.StructDefDictEditor._parse_infosize_input = staticmethod(
        lambda _value: {
            "__type__": "InfoSize",
            "byte": 3,
            "bit": 2
        })
    try:
        converted = editor_module.StructDefDictEditor._row_offset_to_infosize(
            "typed data")
    finally:
        editor_class = editor_module.StructDefDictEditor
        editor_class._parse_infosize_input = original_parser
    assert (converted.byte, converted.bit) == (3, 2)


def test_buttons_are_pack_ordered_above_treeviews():
    """Test that buttons are packed above the treeviews
       in the StructDefDictEditor."""
    with open(
            "src/sltgui/struct_def_dict_editor.py",
            encoding="utf-8",
    ) as source_file:
        source = source_file.read()

    left_buttons_index = source.index("left_btns.pack")
    struct_tree_index = source.index("self.struct_tree.pack")
    field_buttons_index = source.index("field_btns.pack")
    field_tree_index = source.index("self.field_tree.pack")

    assert left_buttons_index < struct_tree_index
    assert field_buttons_index < field_tree_index
