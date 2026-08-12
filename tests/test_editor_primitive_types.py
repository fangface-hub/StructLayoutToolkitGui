"""Tests for the StructDefDictEditor class."""
import importlib
import json
import sys
import types

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
