"""Tests for the BinaryEditorWindow module."""
# pylint: disable=invalid-name,protected-access,too-few-public-methods
import importlib
import sys
import types
from dataclasses import dataclass


def _load_binary_editor_module(monkeypatch):
    sltcodec_module = types.ModuleType("sltcodec")
    sltcodec_module.__path__ = []

    class StubStructDef:
        """A stub StructDef class for testing purposes."""

        def __init__(self, name=""):
            """Initialize the stub StructDef with a name."""
            self.name = name

    sltcodec_module.StructDef = StubStructDef
    sltcodec_module.decode = lambda *args, **kwargs: None
    sltcodec_module.encode = lambda *args, **kwargs: None
    sltcodec_module.EnumDef = object
    sltcodec_module.TypeDict = lambda: types.SimpleNamespace(
        struct_dict={},
        enum_dict={},
    )
    sltcodec_module.StructLayout = (
        lambda struct_def_name, type_dict: types.SimpleNamespace(
            struct_def_name=struct_def_name,
            type_dict=type_dict,
        ))
    sltcodec_module.load_struct_layout = (
        lambda *args, **kwargs: types.SimpleNamespace(
            struct_def_name="StructLayout",
            type_dict=types.SimpleNamespace(struct_dict={}, enum_dict={}),
        ))
    sltcodec_module.save_struct_layout = lambda *args, **kwargs: None

    class DummyInfoSize:
        """A dummy InfoSize class for testing purposes. """

        def __init__(self, byte=0, bit=0):
            """Initialize the dummy InfoSize with byte and bit values."""
            self.byte = byte
            self.bit = bit

        @property
        def bytes(self):
            """Return the byte value."""
            return self.byte

        def __add__(self, other):
            """Add two DummyInfoSize instances
               or a DummyInfoSize and an integer."""
            if isinstance(other, DummyInfoSize):
                return DummyInfoSize(
                    self.byte + other.byte,
                    self.bit + other.bit,
                )
            return DummyInfoSize(self.byte + other, self.bit)

        def __mul__(self, other):
            """Multiply a DummyInfoSize by an integer."""
            if isinstance(other, (int, float)):
                return DummyInfoSize(self.byte * other, self.bit * other)
            return NotImplemented

        def __rmul__(self, other):
            """Support multiplication with the integer on the left."""
            return self.__mul__(other)

        def __lt__(self, other):
            """Compare two DummyInfoSize instances for less than."""
            return (self.byte, self.bit) < (other.byte, other.bit)

        def __gt__(self, other):
            """Compare two DummyInfoSize instances for greater than."""
            return (self.byte, self.bit) > (other.byte, other.bit)

    sltcore_module = types.ModuleType("sltcore")
    sltcore_module.InfoSize = DummyInfoSize
    sltcore_module.bits_get = lambda *args, **kwargs: types.SimpleNamespace(
        to_bytes=bytearray(), )

    class DummyVirtualBytearray:
        """Minimal writable virtual bytearray used by editor tests."""

        def __init__(self, data=b""):
            self.data = bytearray(data)

        def __len__(self):
            return len(self.data)

        def write_slice(self, start, data):
            self.data[start:start + len(data)] = data

    sltcore_module.virtual_bytearray = DummyVirtualBytearray

    tkinterex_module = types.ModuleType("tkinterex")
    tkinterex_module.ConfirmDialog = object
    tkinterex_module.SelectDialog = object
    tkinterex_module.show_modal_window = lambda parent, modal_window: None
    sys.modules["tkinterex"] = tkinterex_module

    treeviewex_module = types.ModuleType("treeviewex")
    treeviewex_module.TreeviewEx = object

    monkeypatch.setitem(sys.modules, "sltcodec", sltcodec_module)
    monkeypatch.setitem(sys.modules, "sltcore", sltcore_module)
    monkeypatch.setitem(sys.modules, "tkinterex", tkinterex_module)
    monkeypatch.setitem(sys.modules, "treeviewex", treeviewex_module)
    # The model module binds InfoSize/StructDef at import time, so drop the
    # cached module too or isinstance checks would use a stale stub class.
    sys.modules.pop("sltgui._struct_instance_model", None)
    sys.modules.pop("sltgui.binary_editor_window", None)

    return importlib.import_module("sltgui.binary_editor_window")


def test_binary_editor_module_and_class_exist(monkeypatch):
    """Test that the BinaryEditorWindow module and class exist."""
    module = _load_binary_editor_module(monkeypatch)

    assert hasattr(module, "BinaryEditorWindow")


def test_infosize_expression_is_available_to_sltcalc(monkeypatch):
    """Test that size expressions can construct and multiply InfoSize."""
    _load_binary_editor_module(monkeypatch)
    from sltcalc import SltEval

    result = SltEval({
        "captured_packet_length": 3
    }).eval("InfoSize(1,0) * captured_packet_length")

    assert result.byte == 3
    assert result.bit == 0


def test_binary_editor_formatters_and_minimum_size(monkeypatch):
    """Test the formatting methods and minimum struct size calculation
       of BinaryEditorWindow."""
    module = _load_binary_editor_module(monkeypatch)
    InfoSize = module.InfoSize

    class DummyFieldDef:
        """A dummy FieldDef class for testing purposes."""

        def __init__(self, name, offset, size, repeat=None, field_type="uint8"):
            """Initialize the dummy FieldDef with name, offset, size, repeat,
               and type."""
            self.name = name
            self.offset = offset
            self.size = size
            self.repeat = repeat
            self.type = field_type

    class DummyStructDef:
        """A dummy StructDef class for testing purposes."""

        def __init__(self, fields):
            """Initialize the dummy StructDef with a list of fields."""
            self.fields = fields

    offset = InfoSize(16, 0)
    assert module.format_infosize(offset) == "16,0"
    assert module.format_infosize(InfoSize(2, 3)) == "2,3"
    assert module.format_infosize(InfoSize(2, 0)) == "2,0"
    assert module.format_type("uint16") == "uint16"
    assert module.format_value(b"\x01\x02") == "01 02"

    struct_def = DummyStructDef([
        DummyFieldDef("id", InfoSize(0, 0), InfoSize(2, 0)),
        DummyFieldDef("data", InfoSize(2, 0), InfoSize(1, 0), repeat=2),
    ])
    assert module.minimum_struct_size(struct_def) == 4

    expression_struct_def = DummyStructDef([
        DummyFieldDef("data",
                      InfoSize(0, 0),
                      InfoSize(1, 0),
                      repeat="packet_length"),
    ])
    try:
        module.minimum_struct_size(expression_struct_def)
    except ValueError as exc:
        assert "repeat expression" in str(exc)
    else:
        raise AssertionError("repeat expressions must not be sized statically")


def test_binary_editor_value_column_is_editable_in_struct_mode(monkeypatch):
    """Test that struct values and raw bytes use their respective editors."""
    module = _load_binary_editor_module(monkeypatch)

    class DummyTree:
        """Record column read-only settings."""

        def __init__(self):
            self.readonly = {}

        def set_readonly_column(self, column_id, readonly=True):
            self.readonly[column_id] = readonly

    editor = object.__new__(module.BinaryEditorWindow)
    editor.tree = DummyTree()

    editor._set_raw_columns(False)
    assert editor.tree.readonly["#2"] is True
    assert editor.tree.readonly["#5"] is False

    editor._set_raw_columns(True)
    assert editor.tree.readonly["#2"] is False
    assert editor.tree.readonly["#5"] is True


def test_binary_editor_tracks_value_cell_started_by_tree(monkeypatch):
    """Test that standard TreeviewEx editing selects the value row."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    editor._instance_path_by_row_id = {"row": (0, )}
    editor.tree = types.SimpleNamespace(
        get_cell_value=lambda _cell: "original value", )

    editor._on_tree_edit_started(("row", "#5"))

    assert editor._value_edit_row_id == "row"
    assert editor._value_edit_original_text == "original value"


def test_binary_editor_raw_size_uses_byte_bit_format(monkeypatch):
    """Test that raw hex rows format their size as byte,bit."""
    module = _load_binary_editor_module(monkeypatch)

    class DummyTree:
        """Record raw rows inserted into the tree."""

        def __init__(self):
            self.rows = []

        def insert(self, parent, index, iid, values):
            self.rows.append((parent, index, iid, values))

    editor = object.__new__(module.BinaryEditorWindow)
    editor.binary_data = bytearray(b"\x01\x02\x03")
    editor.bytes_per_row = 2
    editor.tree = DummyTree()

    editor._insert_raw_bytes()

    assert editor.tree.rows[0][3][-1] == "2,0"
    assert editor.tree.rows[1][3][-1] == "1,0"


def test_binary_editor_tree_column_depth_includes_nested_structs(monkeypatch):
    """Nested struct levels reserve space for every expand indicator."""
    module = _load_binary_editor_module(monkeypatch)

    leaf = types.SimpleNamespace(field_instances=[])
    nested = types.SimpleNamespace(field_instances=[
        types.SimpleNamespace(value=leaf),
    ])
    root = types.SimpleNamespace(field_instances=[
        types.SimpleNamespace(value=nested),
    ])

    assert module.BinaryEditorWindow._instance_tree_depth(root) == 3


def test_binary_editor_replaces_nested_instance_value(monkeypatch):
    """Test that an edited string replaces the matching immutable value."""
    module = _load_binary_editor_module(monkeypatch)

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object

        def with_value(self, value, type_dict=None):
            calls.append((self.value, value, type_dict))
            return type(self)(value)

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list[DummyFieldInstance]

    nested = DummyStructInstance([DummyFieldInstance(1)])
    instance = DummyStructInstance([
        DummyFieldInstance(2),
        DummyFieldInstance(nested),
    ])
    type_dict = object()
    calls = []

    updated = module.replace_instance_value(
        instance,
        (1, 0),
        "0x10",
        type_dict,
    )

    assert updated.field_instances[0].value == 2
    assert updated.field_instances[1].value.field_instances[0].value == 16
    assert instance.field_instances[1].value.field_instances[0].value == 1
    assert calls == [
        (1, 16, type_dict),
        (nested, updated.field_instances[1].value, type_dict),
    ]


def test_binary_editor_formats_and_edits_struct_display_value(monkeypatch):
    """Plugin display values are shown and edited on the struct row."""
    module = _load_binary_editor_module(monkeypatch)

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object

        def with_value(self, value, _type_dict=None):
            return type(self)(value)

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list[DummyFieldInstance]

    timestamp = types.SimpleNamespace(
        field_instances=[],
        display_value="2023-11-14 22:13:20.123456789",
    )
    instance = DummyStructInstance([DummyFieldInstance(timestamp)])

    assert module.format_value(timestamp) == ("2023-11-14 22:13:20.123456789")
    updated = module.replace_instance_value(
        instance,
        (0, ),
        "2023-11-14 22:13:21.987654321",
        object(),
    )
    assert updated.field_instances[0].value.display_value == (
        "2023-11-14 22:13:21.987654321")


def test_binary_editor_shows_timestamp_on_editable_parent_row(monkeypatch):
    """Timestamp parents are editable while raw children are readonly."""
    module = _load_binary_editor_module(monkeypatch)

    class TreeRecorder:

        def __init__(self):
            self.rows = []
            self.readonly_cells = []

        def insert(self, parent, _position, **options):
            row_id = str(len(self.rows))
            self.rows.append((parent, options["values"]))
            return row_id

        def set_readonly_cell(self, cell, readonly):
            if readonly:
                self.readonly_cells.append(cell)

    def field(name, value, field_type):
        return types.SimpleNamespace(
            field_def=types.SimpleNamespace(
                name=name,
                offset=module.InfoSize(),
                size=module.InfoSize(4, 0),
                type=field_type,
            ),
            value=value,
        )

    timestamp = types.SimpleNamespace(
        field_instances=[
            field("timestamp_seconds", 1700000000, "unsigned int"),
            field("timestamp_nanoseconds", 123456789, "unsigned int"),
        ],
        display_value="2023-11-14 22:13:20.123456789",
    )
    instance = types.SimpleNamespace(field_instances=[
        field("pcap_timestamp", timestamp,
              types.SimpleNamespace(name="pcap_timestamp"))
    ], )
    editor = object.__new__(module.BinaryEditorWindow)
    editor.tree = TreeRecorder()
    editor.binary_data = bytearray(8)
    editor._instance_path_by_row_id = {}

    editor._insert_instance(instance, "", module.InfoSize())

    assert editor.tree.rows[0][1][4] == "2023-11-14 22:13:20.123456789"
    assert editor.tree.rows[1][1][4] == "1700000000"
    assert editor.tree.rows[2][1][4] == "123456789"
    assert ("0", editor.VALUE_COLUMN_ID) not in editor.tree.readonly_cells
    assert ("1", editor.VALUE_COLUMN_ID) in editor.tree.readonly_cells
    assert ("2", editor.VALUE_COLUMN_ID) in editor.tree.readonly_cells


def test_binary_editor_value_edit_defers_encoding_until_save(monkeypatch):
    """Test that editing a value updates the instance without encoding."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    updated_instance = object()
    editor._value_edit_row_id = "row"
    editor._value_edit_original_text = "old"
    editor.struct_instance = object()
    editor.struct_layout = types.SimpleNamespace(type_dict=object())
    editor.binary_data = bytearray(b"\x00")
    editor._instance_path_by_row_id = {"row": (0, )}
    monkeypatch.setattr(module, "replace_instance_value",
                        lambda *args: updated_instance)
    editor._encode_with_progress = lambda *args: (_ for _ in ()).throw(
        AssertionError("encoding must be deferred until Save"))
    editor._update_instance_rows = lambda *args: None
    event = types.SimpleNamespace(
        widget=types.SimpleNamespace(get=lambda: "new"), )

    editor._on_value_edit_finished(event)

    assert editor.struct_instance is updated_instance


def test_binary_editor_passes_loaded_type_definitions_to_codec(
    monkeypatch,
    tmp_path,
):
    """Test that the BinaryEditorWindow passes loaded type definitions
       to the codec when opening and saving binary files.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    tmp_path : pathlib.Path
        The temporary directory path provided by pytest for file operations.
    """
    module = _load_binary_editor_module(monkeypatch)
    loaded_type_dict = types.SimpleNamespace(
        struct_dict={"Packet": types.SimpleNamespace(fields=[])},
        enum_dict={"Status": object()},
    )
    loaded_struct_layout = types.SimpleNamespace(
        struct_def_name="Packet",
        type_dict=loaded_type_dict,
    )
    decode_calls = []
    encode_calls = []

    monkeypatch.setattr(
        module,
        "load_struct_layout",
        lambda path: loaded_struct_layout,
    )
    monkeypatch.setattr(
        module.filedialog,
        "askopenfilename",
        lambda **kwargs: "enum_definitions.json",
    )
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args, **_kwargs: decode_calls.append(args) or object(),
    )
    monkeypatch.setattr(
        module,
        "encode",
        lambda *args, **_kwargs: encode_calls.append(args) or bytearray(b"\x01"
                                                                        ),
    )
    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(tmp_path / "output.bin"),
    )
    monkeypatch.setattr(
        module.messagebox,
        "showinfo",
        lambda *args, **kwargs: None,
    )

    class DummyLabel:
        """A dummy label class for testing purposes."""

        def configure(self, **_kwargs):
            """Dummy configure method to simulate label configuration."""
            return None

    editor = object.__new__(module.BinaryEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = tmp_path
    editor.binary_data = bytearray()
    editor.struct_label = DummyLabel()
    editor._select_struct = lambda: "Packet"
    editor._refresh_tree = lambda: None
    editor._run_with_progress = lambda _title, worker_fn: worker_fn(
        lambda _progress: None)
    editor._open_struct_layout()
    editor._new_binary()

    assert editor.struct_layout.type_dict is loaded_type_dict
    assert decode_calls[0][0].type_dict is loaded_type_dict
    assert decode_calls[0][0].struct_def_name == "Packet"

    editor._save_binary_as()

    assert encode_calls[0][0].type_dict is loaded_type_dict
    assert encode_calls[0][0].struct_def_name == "Packet"


def test_opening_struct_layout_decodes_loaded_binary(monkeypatch, tmp_path):
    """Test that opening a layout decodes binary data loaded in raw mode."""
    module = _load_binary_editor_module(monkeypatch)
    loaded_layout = module.StructLayout(
        struct_def_name="Packet",
        type_dict=types.SimpleNamespace(
            struct_dict={"Packet": object()},
            enum_dict={},
        ),
    )
    decoded_instance = object()
    decode_calls = []

    monkeypatch.setattr(module.filedialog, "askopenfilename",
                        lambda **_kwargs: "StructLayout.json")
    monkeypatch.setattr(module, "load_struct_layout",
                        lambda _path: loaded_layout)
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args, **_kwargs: decode_calls.append(args) or decoded_instance,
    )

    editor = object.__new__(module.BinaryEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = tmp_path
    editor.binary_data = bytearray(b"\x00\x00\x00\x00")
    editor.struct_instance = None
    editor.struct_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None, )
    editor._refresh_tree = lambda: None
    editor._run_with_progress = lambda _title, worker_fn: worker_fn(
        lambda _progress: None)

    editor._open_struct_layout()

    assert decode_calls == [(loaded_layout, editor.binary_data)]
    assert editor.struct_instance is decoded_instance


def test_binary_editor_uses_shared_modal_window_helper(monkeypatch):
    """Test that the BinaryEditorWindow uses the shared show_modal_window helper
       function to display modal windows.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    calls = []

    def fake_show_modal_window(parent, modal_window):
        """Fake show_modal_window function to capture calls for testing."""
        calls.append((parent, modal_window))

    monkeypatch.setattr(module, "show_modal_window", fake_show_modal_window)

    editor = object.__new__(module.BinaryEditorWindow)
    modal = object()
    show_modal_window = module.show_modal_window
    show_modal_window(editor, modal)

    assert calls == [(editor, modal)]


def test_binary_editor_tracks_current_struct_layout(monkeypatch):
    """Test that the BinaryEditorWindow tracks the current StructLayout
       and updates the struct label accordingly.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    calls = []

    class DummyLabel:
        """A dummy label class for testing purposes."""

        def configure(self, **_kwargs):
            """Dummy configure method to simulate label configuration."""
            return None

    editor = object.__new__(module.BinaryEditorWindow)
    editor.binary_data = bytearray(b"\x00")
    editor.struct_layout = module.StructLayout(
        struct_def_name="",
        type_dict=types.SimpleNamespace(
            struct_dict={"Packet": object()},
            enum_dict={},
        ),
    )
    editor.struct_label = DummyLabel()
    editor._refresh_tree = lambda: None
    editor._select_struct = lambda: "Packet"
    editor.struct_instance = None
    editor._run_with_progress = lambda _title, worker_fn: worker_fn(
        lambda _progress: None)

    monkeypatch.setattr(
        module,
        "decode",
        lambda layout, data, **_kwargs: calls.append(layout) or object(),
    )

    editor._select_struct_definition()

    assert editor.struct_layout.struct_def_name == "Packet"
    assert calls[0] is editor.struct_layout


def test_binary_editor_opens_definition_editors_in_child_windows(monkeypatch):
    """Test that the BinaryEditorWindow opens struct and enum definition editors
       in child windows using the show_modal_window helper function.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    opened_editors = []

    class DummyStructDefDictEditor:
        """A dummy StructDefDictEditor class for testing purposes."""

        def __init__(self, parent, *, type_dict):
            """Initialize the dummy StructDefDictEditor and record
               the opened editor.
            Parameters
            ----------
            parent : object
                The parent window for the editor.
            type_dict : object
                The type dictionary to be edited.
            """

            opened_editors.append(("struct", parent, type_dict))

    class DummyEnumDefDictEditor:
        """A dummy EnumDefDictEditor class for testing purposes."""

        def __init__(self, parent, *, type_dict):
            """Initialize the dummy EnumDefDictEditor
               and record the opened editor.
            Parameters
            ----------
            parent : object
                The parent window for the editor.
            type_dict : object
                The type dictionary to be edited.
            """

            opened_editors.append(("enum", parent, type_dict))

    def fake_show_modal_window(parent, modal_window):
        """Fake show_modal_window function to capture calls for testing.
        Parameters
        ----------
        parent : object
            The parent window for the modal window.
        modal_window : object
            The modal window to be displayed.
        """
        modal_windows.append((parent, modal_window))

    monkeypatch.setattr(module, "show_modal_window", fake_show_modal_window)

    struct_editor_module = types.ModuleType("sltgui.struct_def_dict_editor")
    struct_editor_module.StructDefDictEditor = DummyStructDefDictEditor
    enum_editor_module = types.ModuleType("sltgui.enum_def_dict_editor")
    enum_editor_module.EnumDefDictEditor = DummyEnumDefDictEditor
    monkeypatch.setitem(
        sys.modules,
        "sltgui.struct_def_dict_editor",
        struct_editor_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "sltgui.enum_def_dict_editor",
        enum_editor_module,
    )
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_layout = module.StructLayout(
        struct_def_name="",
        type_dict=object(),
    )
    modal_windows = []
    editor._open_struct_definition_editor()
    editor._open_enum_definition_editor()

    assert [editor_name for editor_name, *_ in opened_editors] == [
        "struct",
        "enum",
    ]
    assert [parent for _, parent, _ in opened_editors] == [
        editor,
        editor,
    ]
    assert [type_dict for _, _, type_dict in opened_editors] == [
        editor.struct_layout.type_dict,
        editor.struct_layout.type_dict,
    ]
    assert [modal_window[1].__class__ for modal_window in modal_windows] == [
        DummyStructDefDictEditor,
        DummyEnumDefDictEditor,
    ]
    assert [modal_window[0] for modal_window in modal_windows] == [
        editor,
        editor,
    ]


def test_binary_editor_opens_editors_when_run_as_script(monkeypatch):
    """Test that the BinaryEditorWindow opens struct and enum definition editors
       when run as a script, using the show_modal_window helper function.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    opened_editors = []

    class DummyEditor:
        """A dummy editor class for testing purposes."""

        def __init__(self, _parent, **kwargs):
            """Initialize the dummy editor and record the opened editor.
            Parameters
            ----------
            _parent : object
                The parent window for the editor.
            **kwargs : dict
                Additional keyword arguments for the editor.
            """
            opened_editors.append(kwargs["type_dict"])

    def fake_show_modal_window(parent, modal_window):
        """Fake show_modal_window function to capture calls for testing.
        Parameters
        ----------
        parent : object
            The parent window for the modal window.
        modal_window : object
            The modal window to be displayed.
        """
        modal_windows.append((parent, modal_window))

    monkeypatch.setattr(module, "show_modal_window", fake_show_modal_window)

    struct_editor_module = types.ModuleType("struct_def_dict_editor")
    struct_editor_module.StructDefDictEditor = DummyEditor
    enum_editor_module = types.ModuleType("enum_def_dict_editor")
    enum_editor_module.EnumDefDictEditor = DummyEditor
    monkeypatch.setitem(
        sys.modules,
        "struct_def_dict_editor",
        struct_editor_module,
    )
    monkeypatch.setitem(sys.modules, "enum_def_dict_editor", enum_editor_module)
    monkeypatch.setattr(module, "__package__", None)

    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_layout = module.StructLayout(
        struct_def_name="",
        type_dict=object(),
    )
    modal_windows = []
    editor._open_struct_definition_editor()
    editor._open_enum_definition_editor()

    assert opened_editors == [
        editor.struct_layout.type_dict,
        editor.struct_layout.type_dict,
    ]
    assert [parent for parent, _ in modal_windows] == [editor, editor]
    assert [modal_window.__class__ for _, modal_window in modal_windows] == [
        DummyEditor,
        DummyEditor,
    ]


def test_binary_editor_file_menu_uses_binary_file_commands(monkeypatch):
    """Test that the BinaryEditorWindow file menu uses the correct commands
       for new, open, and save binary file operations.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    menus = []

    class DummyMenu:
        """A dummy Menu class for testing purposes."""

        def __init__(self, _parent, **_kwargs):
            """Initialize the dummy Menu and record the created menu.
            Parameters
            ----------
            _parent : object
                The parent window for the menu.
            **_kwargs : dict
                    Additional keyword arguments for the menu.
            """
            self.commands = []
            self.cascades = []
            menus.append(self)

        def add_command(self, **kwargs):
            """Add a command to the dummy menu and record the command.
            Parameters
            ----------
            **kwargs : dict
                Additional keyword arguments for the command.
            """
            self.commands.append(kwargs)

        def add_separator(self):
            """Add a separator to the dummy menu and record the separator."""
            self.commands.append({"label": "separator"})

        def add_cascade(self, **kwargs):
            """Add a cascade to the dummy menu and record the cascade.
            Parameters
            ----------
            **kwargs : dict
                Additional keyword arguments for the cascade.
            """
            self.cascades.append(kwargs)

    class DummyMaster:
        """A dummy master class for testing purposes."""

        def destroy(self):
            """Dummy destroy method to simulate master destruction."""
            return None

    monkeypatch.setattr(module.tk, "Menu", DummyMenu)
    editor = object.__new__(module.BinaryEditorWindow)
    editor.master = DummyMaster()
    editor.config = lambda **kwargs: None
    editor._new_binary = object()
    editor._open_binary = object()
    editor._save_binary = object()
    editor._save_binary_as = object()
    editor._export_tree_to_csv = object()
    editor._export_tree_to_json = object()
    editor._open_struct_layout = object()
    editor._save_struct_layout = object()
    editor._save_struct_layout_as = object()
    editor._select_struct_definition = object()
    editor._open_struct_definition_editor = object()
    editor._open_enum_definition_editor = object()

    editor._build_menu()

    file_menu = menus[1]
    assert [command["label"] for command in file_menu.commands] == [
        "New Binary...",
        "Open Binary...",
        "separator",
        "Save Binary",
        "Save Binary As...",
        "Export to CSV...",
        "Export to JSON...",
        "separator",
        "Exit",
    ]
    assert [cascade["label"] for cascade in menus[0].cascades] == [
        "File",
        "Type Definition",
    ]
    type_definition_menu = menus[2]
    assert [command["label"] for command in type_definition_menu.commands] == [
        "Open StructLayout...",
        "separator",
        "Save StructLayout",
        "Save StructLayout As...",
        "separator",
        "Select Struct...",
        "separator",
        "Struct Definitions...",
        "Enum Definitions...",
    ]
    assert [cascade["label"]
            for cascade in type_definition_menu.cascades] == ["Load Resource"]
    resource_menu = menus[3]
    assert [command["label"] for command in resource_menu.commands] == [
        "PCAP",
        "PCAPNG",
    ]


def test_load_struct_layout_resource_decodes_and_saves_as(
        monkeypatch, tmp_path):
    """A bundled layout is decoded but has no source file to overwrite."""
    module = _load_binary_editor_module(monkeypatch)
    layout = module.StructLayout(
        struct_def_name="Packet",
        type_dict=types.SimpleNamespace(
            struct_dict={"Packet": object()},
            enum_dict={},
        ),
    )
    decoded_instance = object()
    save_as_calls = []
    editor = object.__new__(module.BinaryEditorWindow)
    editor.binary_data = bytearray(b"\x01")
    editor.struct_layout_file = tmp_path / "previous.json"
    editor.struct_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None, )
    editor._refresh_tree = lambda: None
    editor._decode_with_progress = lambda *_args: decoded_instance
    editor._save_struct_layout_as = lambda: save_as_calls.append(True)

    editor._load_struct_layout_resource(lambda: layout)
    editor._save_struct_layout()

    assert editor.struct_layout is layout
    assert editor.struct_instance is decoded_instance
    assert editor.struct_layout_file is None
    assert save_as_calls == [True]


def test_binary_editor_file_menu_hides_binary_commands_when_masked(monkeypatch):
    """Test that a Return menu replaces the File menu when masked."""
    module = _load_binary_editor_module(monkeypatch)
    menus = []

    class DummyMenu:
        """A dummy Menu class for testing purposes."""

        def __init__(self, _parent, **_kwargs):
            self.commands = []
            self.cascades = []
            menus.append(self)

        def add_command(self, **kwargs):
            self.commands.append(kwargs)

        def add_separator(self):
            self.commands.append({"label": "separator"})

        def add_cascade(self, **kwargs):
            self.cascades.append(kwargs)

    class DummyMaster:
        """A dummy master class for testing purposes."""

        def destroy(self):
            return None

    monkeypatch.setattr(module.tk, "Menu", DummyMenu)
    editor = object.__new__(module.BinaryEditorWindow)
    editor.master = DummyMaster()
    editor.config = lambda **kwargs: None
    editor._binary_file_masked = True
    editor._return_without_saving = object()
    editor._return_with_saving = object()
    editor._open_struct_layout = object()
    editor._save_struct_layout = object()
    editor._save_struct_layout_as = object()
    editor._select_struct_definition = object()
    editor._open_struct_definition_editor = object()
    editor._open_enum_definition_editor = object()

    editor._build_menu()

    return_menu = menus[1]
    assert [command["label"] for command in return_menu.commands] == [
        "Return without saving",
        "Return with saving",
    ]
    assert [cascade["label"] for cascade in menus[0].cascades] == [
        "Return",
        "Type Definition",
    ]


def test_save_overwrites_open_binary_without_dialog(monkeypatch, tmp_path):
    """Test that Save writes the currently open binary file directly."""
    module = _load_binary_editor_module(monkeypatch)
    binary_file = tmp_path / "opened.bin"
    binary_file.write_bytes(b"old")
    editor = object.__new__(module.BinaryEditorWindow)
    editor.binary_file = binary_file
    editor.binary_data = bytearray(b"new")
    editor.struct_instance = None
    editor.struct_layout = module.StructLayout(
        struct_def_name="",
        type_dict=module.TypeDict(),
    )
    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs:
        (_ for _ in ()).throw(AssertionError("Save As dialog must not open")),
    )
    monkeypatch.setattr(module.messagebox, "showinfo",
                        lambda *args, **kwargs: None)

    editor._save_binary()

    assert binary_file.read_bytes() == b"new"


def test_save_overwrites_open_struct_layout_without_dialog(
    monkeypatch,
    tmp_path,
):
    """Test that Save writes the currently open StructLayout directly."""
    module = _load_binary_editor_module(monkeypatch)
    layout_file = tmp_path / "StructLayout.json"
    save_calls = []
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_layout_file = layout_file
    editor.struct_layout = module.StructLayout(
        struct_def_name="Packet",
        type_dict=module.TypeDict(),
    )
    monkeypatch.setattr(
        module,
        "save_struct_layout",
        lambda *args: save_calls.append(args),
    )
    monkeypatch.setattr(
        module.filedialog,
        "asksaveasfilename",
        lambda **_kwargs:
        (_ for _ in ()).throw(AssertionError("Save As dialog must not open")),
    )
    monkeypatch.setattr(module.messagebox, "showinfo",
                        lambda *args, **kwargs: None)

    editor._save_struct_layout()

    assert save_calls == [(editor.struct_layout, layout_file)]


def test_selecting_struct_redecodes_loaded_binary(monkeypatch):
    """Test that selecting a struct in the BinaryEditorWindow
       re-decodes the loaded binary data
       using the selected struct definition.
    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        The pytest monkeypatch fixture for modifying module attributes.
    """
    module = _load_binary_editor_module(monkeypatch)
    decode_calls = []

    class DummyLabel:
        """A dummy label class for testing purposes."""

        def __init__(self):
            """Initialize the dummy label."""
            self.text = ""

        def configure(self, **kwargs):
            """Dummy configure method to simulate label configuration."""
            self.text = kwargs["text"]

    struct_def = object()
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_layout = module.StructLayout(
        struct_def_name="",
        type_dict=types.SimpleNamespace(
            struct_dict={"Packet": struct_def},
            enum_dict={"Status": object()},
        ),
    )
    editor.binary_data = bytearray(b"\x01")
    editor.struct_label = DummyLabel()
    editor._select_struct = lambda: "Packet"
    editor._refresh_tree = lambda: None
    editor._run_with_progress = lambda _title, worker_fn: worker_fn(
        lambda _progress: None)
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args, **_kwargs: decode_calls.append(args) or object(),
    )

    editor._select_struct_definition()

    assert editor.struct_instance is not None
    assert editor.struct_label.text == "Struct: Packet"
    assert decode_calls[0][0].struct_def_name == "Packet"
    assert decode_calls[0][0].type_dict is editor.struct_layout.type_dict


def test_redecode_binary_refreshes_current_instance(monkeypatch):
    """Test re-decoding with the current binary and updated definitions."""
    module = _load_binary_editor_module(monkeypatch)
    decoded_instance = object()
    decode_calls = []
    refresh_calls = []
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_layout = module.StructLayout(
        struct_def_name="Packet",
        type_dict=types.SimpleNamespace(
            struct_dict={"Packet": object()},
            enum_dict={"Status": object()},
        ),
    )
    editor.binary_data = bytearray(b"\x01")
    editor.struct_instance = object()
    editor._refresh_tree = lambda: refresh_calls.append(True)
    editor._run_with_progress = lambda _title, worker_fn: worker_fn(
        lambda _progress: None)
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args, **_kwargs: decode_calls.append(args) or decoded_instance,
    )

    editor._redecode_binary()

    assert decode_calls == [(editor.struct_layout, editor.binary_data)]
    assert editor.struct_instance is decoded_instance
    assert refresh_calls == [True]


def test_decode_error_uses_tkinterex_dialog(monkeypatch):
    """Test that decode errors are shown with tkinterex's modal dialog."""
    module = _load_binary_editor_module(monkeypatch)
    dialog_calls = []

    class DummyDialog:
        """Capture the tkinterex error dialog arguments."""

        def __init__(self, parent, message, buttons):
            dialog_calls.append((parent, message, buttons))

        def title(self, title):
            dialog_calls.append(title)

        def show(self):
            dialog_calls.append("shown")

    monkeypatch.setattr(module, "ConfirmDialog", DummyDialog)
    editor = object.__new__(module.BinaryEditorWindow)
    error = NameError("Undefined variable: magic_number")

    editor._show_decode_error(error)

    assert dialog_calls == [
        (editor, "Undefined variable: magic_number", [("ok", "OK")]),
        "Decode Error",
        "shown",
    ]


def test_collect_tree_rows_for_export_flattens_nested_rows(monkeypatch):
    """Test that nested tree rows are flattened with level and path."""
    module = _load_binary_editor_module(monkeypatch)

    class DummyTree:
        """Minimal tree API used by _collect_tree_rows_for_export."""

        def __init__(self):
            self.children = {
                "": ["r1", "r2"],
                "r1": ["r1_1"],
                "r1_1": [],
                "r2": [],
            }
            self.values = {
                "r1": ("0,0", "AA", "root", "uint8", "1", "1,0"),
                "r1_1": (
                    "1,0",
                    "BB",
                    "child",
                    "uint8",
                    "2",
                    "1,0",
                ),
                "r2": ("2,0", "CC", "second", "uint8", "3", "1,0"),
            }

        def get_children(self, parent_id):
            return self.children[parent_id]

        def item(self, row_id, key):
            assert key == "values"
            return self.values[row_id]

    editor = object.__new__(module.BinaryEditorWindow)
    editor.tree = DummyTree()

    rows = editor._collect_tree_rows_for_export()

    assert rows == [
        (0, "root", "0,0", "AA", "root", "uint8", "1", "1,0"),
        (1, "root.child", "1,0", "BB", "child", "uint8", "2", "1,0"),
        (0, "second", "2,0", "CC", "second", "uint8", "3", "1,0"),
    ]


def test_collect_tree_nodes_for_json_preserves_nested_structure(monkeypatch):
    """Test that nested tree rows are exported as nested JSON nodes."""
    module = _load_binary_editor_module(monkeypatch)

    class DummyTree:
        """Minimal tree API used by _collect_tree_nodes_for_json."""

        def __init__(self):
            self.children = {
                "": ["r1", "r2"],
                "r1": ["r1_1"],
                "r1_1": [],
                "r2": [],
            }
            self.values = {
                "r1": ("0,0", "AA", "root", "uint8", "1", "1,0"),
                "r1_1": (
                    "1,0",
                    "BB",
                    "child",
                    "uint8",
                    "2",
                    "1,0",
                ),
                "r2": ("2,0", "CC", "second", "uint8", "3", "1,0"),
            }

        def get_children(self, parent_id):
            return self.children[parent_id]

        def item(self, row_id, key):
            assert key == "values"
            return self.values[row_id]

    editor = object.__new__(module.BinaryEditorWindow)
    editor.tree = DummyTree()

    nodes = editor._collect_tree_nodes_for_json()

    assert nodes == [{
        "level":
        0,
        "path":
        "root",
        "offset":
        "0,0",
        "hex":
        "AA",
        "name":
        "root",
        "type":
        "uint8",
        "value":
        "1",
        "size":
        "1,0",
        "children": [{
            "level": 1,
            "path": "root.child",
            "offset": "1,0",
            "hex": "BB",
            "name": "child",
            "type": "uint8",
            "value": "2",
            "size": "1,0",
            "children": [],
        }],
    }, {
        "level": 0,
        "path": "second",
        "offset": "2,0",
        "hex": "CC",
        "name": "second",
        "type": "uint8",
        "value": "3",
        "size": "1,0",
        "children": [],
    }]


def test_field_instance_at_path_navigates_nested_fields(monkeypatch):
    """Test that field_instance_at_path follows a nested field path."""
    module = _load_binary_editor_module(monkeypatch)

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list

    nested_field = DummyFieldInstance(bytearray(b"\x01\x02"))
    nested = DummyStructInstance([DummyFieldInstance(1), nested_field])
    struct_instance = DummyStructInstance([DummyFieldInstance(nested)])

    field_instance = module.field_instance_at_path(struct_instance, (0, 1))

    assert field_instance is nested_field


def test_tree_right_click_opens_menu_for_bytearray_hex_cell(monkeypatch):
    """Test that right-clicking a bytearray field's hex cell shows a menu."""
    module = _load_binary_editor_module(monkeypatch)

    class DummyMenu:
        """Record menu commands and the popup position."""

        instances = []

        def __init__(self, _parent, **_kwargs):
            self.commands = []
            self.popup_at = None
            DummyMenu.instances.append(self)

        def add_command(self, **kwargs):
            self.commands.append(kwargs)

        def tk_popup(self, x_root, y_root):
            self.popup_at = (x_root, y_root)

    monkeypatch.setattr(module.tk, "Menu", DummyMenu)

    @dataclass(frozen=True)
    class DummyFieldDef:
        type: str

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object
        field_def: object

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list

    # decode() yields immutable bytes for bytearray-typed fields.
    field_instance = DummyFieldInstance(b"\x01\x02", DummyFieldDef("bytearray"))
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_instance = DummyStructInstance([field_instance])
    editor._instance_path_by_row_id = {"row": (0, )}
    editor.tree = types.SimpleNamespace(
        identify_row=lambda _y: "row",
        identify_column=lambda _x: module.BinaryEditorWindow.HEX_COLUMN_ID,
    )
    opened_paths = []
    editor._open_bytearray_field_editor = opened_paths.append
    event = types.SimpleNamespace(x=1, y=1, x_root=10, y_root=20)

    editor._on_tree_right_click(event)

    assert len(DummyMenu.instances) == 1
    menu = DummyMenu.instances[0]
    assert [command["label"] for command in menu.commands] == [
        "Open BinaryEditorWindow",
    ]
    assert menu.popup_at == (10, 20)

    menu.commands[0]["command"]()

    assert opened_paths == [(0, )]


def test_tree_right_click_ignores_non_bytearray_and_non_hex_cells(monkeypatch):
    """Test that the context menu is skipped for irrelevant cells."""
    module = _load_binary_editor_module(monkeypatch)
    menu_created = []
    monkeypatch.setattr(
        module.tk,
        "Menu",
        lambda *args, **kwargs: menu_created.append(True),
    )

    @dataclass(frozen=True)
    class DummyFieldDef:
        type: str

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object
        field_def: object

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list

    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_instance = DummyStructInstance(
        [DummyFieldInstance(1, DummyFieldDef("uint8"))])
    editor._instance_path_by_row_id = {"row": (0, )}

    # Non-hex column is ignored even for a bytearray field.
    editor.tree = types.SimpleNamespace(
        identify_row=lambda _y: "row",
        identify_column=lambda _x: module.BinaryEditorWindow.VALUE_COLUMN_ID,
    )
    editor._on_tree_right_click(types.SimpleNamespace(x=1, y=1))
    assert menu_created == []

    # Hex column of a non-bytearray field does not open a menu.
    editor.tree = types.SimpleNamespace(
        identify_row=lambda _y: "row",
        identify_column=lambda _x: module.BinaryEditorWindow.HEX_COLUMN_ID,
    )
    editor._on_tree_right_click(types.SimpleNamespace(x=1, y=1))
    assert menu_created == []


def test_open_bytearray_field_editor_writes_edited_bytes_back(monkeypatch):
    """Test that edits made in the nested editor are written back."""
    module = _load_binary_editor_module(monkeypatch)

    @dataclass(frozen=True)
    class DummyFieldDef:
        type: str

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object
        field_def: object

        def with_value(self, value, type_dict=None):
            with_value_calls.append((value, type_dict))
            return type(self)(value, self.field_def)

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list

    with_value_calls = []
    # decode() yields immutable bytes for bytearray-typed fields.
    field_instance = DummyFieldInstance(b"\x01\x02", DummyFieldDef("bytearray"))
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_instance = DummyStructInstance([field_instance])
    editor.apl_dir = "apl_dir"
    editor.data_dir = "data_dir"
    editor.struct_layout = types.SimpleNamespace(type_dict="type_dict")
    updated_rows_calls = []
    editor._update_instance_rows = lambda *args: updated_rows_calls.append(args)

    created_kwargs = {}

    class DummyEditor:
        """Record constructor arguments used to open the nested editor."""

        def __init__(self, parent, **kwargs):
            created_kwargs["parent"] = parent
            created_kwargs.update(kwargs)

    modal_calls = []

    def fake_show_modal_window(parent, editor_window):
        # Simulate the user editing the bytes and choosing "Return with saving".
        created_kwargs["input_data"][0] = 0xFF
        editor_window._save_on_close = True
        modal_calls.append((parent, editor_window))

    monkeypatch.setattr(module, "BinaryEditorWindow", DummyEditor)
    monkeypatch.setattr(module, "show_modal_window", fake_show_modal_window)

    editor._open_bytearray_field_editor((0, ))

    assert created_kwargs["parent"] is editor
    assert created_kwargs["apl_dir"] == "apl_dir"
    assert created_kwargs["data_dir"] == "data_dir"
    assert created_kwargs["input_data"] == bytearray(b"\xff\x02")
    assert len(modal_calls) == 1
    assert modal_calls[0][0] is editor
    assert with_value_calls == [(b"\xff\x02", "type_dict")]
    assert editor.struct_instance.field_instances[0].value == b"\xff\x02"
    assert len(updated_rows_calls) == 1


def test_open_bytearray_field_editor_discards_edits_without_saving(monkeypatch):
    """Test that choosing Return without saving keeps the original value."""
    module = _load_binary_editor_module(monkeypatch)

    @dataclass(frozen=True)
    class DummyFieldDef:
        type: str

    @dataclass(frozen=True)
    class DummyFieldInstance:
        value: object
        field_def: object

        def with_value(self, value, type_dict=None):
            raise AssertionError("with_value must not be called")

    @dataclass(frozen=True)
    class DummyStructInstance:
        field_instances: list

    original_instance = DummyStructInstance(
        [DummyFieldInstance(b"\x01\x02", DummyFieldDef("bytearray"))])
    editor = object.__new__(module.BinaryEditorWindow)
    editor.struct_instance = original_instance
    editor.apl_dir = "apl_dir"
    editor.data_dir = "data_dir"
    editor.struct_layout = types.SimpleNamespace(type_dict="type_dict")
    editor._update_instance_rows = lambda *args: (_ for _ in ()).throw(
        AssertionError("rows must not be refreshed"))

    class DummyEditor:
        """Record constructor arguments used to open the nested editor."""

        def __init__(self, parent, **kwargs):
            pass

    def fake_show_modal_window(_parent, editor_window):
        # Simulate the user choosing "Return without saving".
        editor_window._save_on_close = False

    monkeypatch.setattr(module, "BinaryEditorWindow", DummyEditor)
    monkeypatch.setattr(module, "show_modal_window", fake_show_modal_window)

    editor._open_bytearray_field_editor((0, ))

    assert editor.struct_instance is original_instance


def test_exit_destroys_master_for_top_level_editor(monkeypatch):
    """Test that Exit closes the whole app for the top-level editor."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    destroy_calls = []
    editor.master = types.SimpleNamespace(
        destroy=lambda: destroy_calls.append(True))

    editor._exit()

    assert destroy_calls == [True]


def test_return_without_saving_sets_flag_and_closes(monkeypatch):
    """Test that Return without saving marks edits to be discarded."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    editor._save_on_close = True
    destroy_calls = []
    editor.destroy = lambda: destroy_calls.append(True)

    editor._return_without_saving()

    assert editor._save_on_close is False
    assert destroy_calls == [True]


def test_return_with_saving_sets_flag_and_closes(monkeypatch):
    """Test that Return with saving marks edits to be kept."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    editor._save_on_close = False
    destroy_calls = []
    editor.destroy = lambda: destroy_calls.append(True)

    editor._return_with_saving()

    assert editor._save_on_close is True
    assert destroy_calls == [True]


def test_return_with_saving_encodes_structured_data_in_place(monkeypatch):
    """Structured child edits are encoded into the caller's bytearray."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    original_data = bytearray(b"old")
    editor.binary_data = original_data
    editor.struct_instance = object()
    editor.struct_layout = object()
    editor._save_on_close = False
    editor._encode_with_progress = lambda *_args: bytearray(b"new-data")
    editor.destroy = lambda: None

    editor._return_with_saving()

    assert editor.binary_data is original_data
    assert original_data == b"new-data"
    assert editor._save_on_close is True


def test_return_with_saving_writes_to_virtual_data(monkeypatch):
    """Structured edits write through virtual packet storage."""
    module = _load_binary_editor_module(monkeypatch)
    editor = object.__new__(module.BinaryEditorWindow)
    original_data = module.virtual_bytearray(b"old")
    editor.binary_data = original_data
    editor.struct_instance = object()
    editor.struct_layout = object()
    editor._save_on_close = False
    editor._encode_with_progress = lambda *_args: bytearray(b"new")
    editor.destroy = lambda: None

    editor._return_with_saving()

    assert editor.binary_data is original_data
    assert original_data.data == b"new"
    assert editor._save_on_close is True
