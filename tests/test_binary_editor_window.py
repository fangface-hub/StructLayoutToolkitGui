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

    tkinterex_module = types.ModuleType("tkinterex")
    tkinterex_module.SelectDialog = object
    tkinterex_module.show_modal_window = lambda parent, modal_window: None
    sys.modules["tkinterex"] = tkinterex_module

    treeviewex_module = types.ModuleType("treeviewex")
    treeviewex_module.TreeviewEx = object

    monkeypatch.setitem(sys.modules, "sltcodec", sltcodec_module)
    monkeypatch.setitem(sys.modules, "sltcore", sltcore_module)
    monkeypatch.setitem(sys.modules, "tkinterex", tkinterex_module)
    monkeypatch.setitem(sys.modules, "treeviewex", treeviewex_module)
    sys.modules.pop("sltgui.binary_editor_window", None)

    return importlib.import_module("sltgui.binary_editor_window")


def test_binary_editor_module_and_class_exist(monkeypatch):
    """Test that the BinaryEditorWindow module and class exist."""
    module = _load_binary_editor_module(monkeypatch)

    assert hasattr(module, "BinaryEditorWindow")


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
    assert module.BinaryEditorWindow._format_offset(offset) == "0x10"
    assert module.BinaryEditorWindow._format_size(InfoSize(2, 0)) == "2,0"
    assert module.BinaryEditorWindow._format_type("uint16") == "uint16"
    assert module.BinaryEditorWindow._format_value(b"\x01\x02") == "01 02"

    struct_def = DummyStructDef([
        DummyFieldDef("id", InfoSize(0, 0), InfoSize(2, 0)),
        DummyFieldDef("data", InfoSize(2, 0), InfoSize(1, 0), repeat=2),
    ])
    assert module.BinaryEditorWindow._minimum_struct_size(struct_def) == 4


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

    updated = module.BinaryEditorWindow._replace_instance_value(
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
        lambda *args: decode_calls.append(args) or object(),
    )
    monkeypatch.setattr(
        module,
        "encode",
        lambda *args: encode_calls.append(args) or bytearray(b"\x01"),
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
        lambda *args: decode_calls.append(args) or decoded_instance,
    )

    editor = object.__new__(module.BinaryEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = tmp_path
    editor.binary_data = bytearray(b"\x00\x00\x00\x00")
    editor.struct_instance = None
    editor.struct_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None, )
    editor._refresh_tree = lambda: None

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

    monkeypatch.setattr(
        module,
        "decode",
        lambda layout, data: calls.append(layout) or object(),
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
        "Save StructLayout",
        "Save StructLayout As...",
        "separator",
        "Select Struct...",
        "separator",
        "Struct Definitions...",
        "Enum Definitions...",
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
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args: decode_calls.append(args) or object(),
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
    monkeypatch.setattr(
        module,
        "decode",
        lambda *args: decode_calls.append(args) or decoded_instance,
    )

    editor._redecode_binary()

    assert decode_calls == [(editor.struct_layout, editor.binary_data)]
    assert editor.struct_instance is decoded_instance
    assert refresh_calls == [True]
