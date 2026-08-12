"""Tests for direct and package loading of the packet data editor."""
import json
import runpy
import types
from pathlib import Path

import sltgui.packet_data_editor_window as packet_editor_module
from sltgui.packet_data_editor_window import PacketDataEditorWindow


def test_packet_data_editor_supports_direct_script_loading(monkeypatch):
    """Direct script mode resolves sibling modules without a package."""
    module_path = (Path(__file__).parents[1] / "src" / "sltgui" /
                   "packet_data_editor_window.py")
    monkeypatch.syspath_prepend(str(module_path.parent))

    namespace = runpy.run_path(module_path, run_name="direct_import_test")

    assert "PacketDataEditorWindow" in namespace


def test_hex_is_the_last_packet_list_column():
    """The last column in the packet list and detail view should be 'hex'."""
    assert PacketDataEditorWindow.COLUMNS[-1] == "hex"
    assert PacketDataEditorWindow.DETAIL_COLUMNS[-1] == "hex"
    assert PacketDataEditorWindow.PACKET_HEX_COLUMN_ID == "#10"


def test_packet_editor_does_not_depend_on_binary_editor():
    """The packet data editor should not depend on the binary editor."""
    assert not hasattr(packet_editor_module, "BinaryEditorWindow")


def test_packet_editor_uses_its_own_settings_section(tmp_path):
    """Packet directory settings do not overwrite BinaryEditor settings."""
    settings_file = tmp_path / "setting.json"
    settings_file.write_text(
        json.dumps({"BinaryEditor": {
            "data_dir": "binary-dir"
        }}),
        encoding="utf-8",
    )
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path

    editor._remember_data_dir(capture_dir / "capture.pcap")

    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings["BinaryEditor"]["data_dir"] == "binary-dir"
    assert settings["PacketDataEditor"]["data_dir"] == (capture_dir.as_posix())
    assert editor._load_dir_setting() == capture_dir


def test_open_capture_applies_decode_plugin(monkeypatch, tmp_path):
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = Path(".")
    editor._lua_plugin_manager = types.SimpleNamespace(
        apply_decode=lambda instance: f"plugin:{instance}")
    editor._refresh_packets = lambda *_args: None
    opened = []
    document = types.SimpleNamespace()

    def open_capture(path, decode_transform):
        opened.append((path, decode_transform("capture-instance")))
        return document

    monkeypatch.setattr(packet_editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "capture.pcap")
    monkeypatch.setattr(packet_editor_module.CaptureDocument, "open",
                        open_capture)

    editor._open_capture()

    assert opened == [("capture.pcap", "plugin:capture-instance")]
    assert editor.document is document


def test_packet_hex_edit_writes_back_in_this_window():
    """Editing the packet hex view should write back changes to the packet."""
    editor = object.__new__(PacketDataEditorWindow)
    writes = []
    packet = types.SimpleNamespace(
        sequence=4,
        replace_data=lambda capture, data: writes.append((capture, data)),
    )
    editor.document = types.SimpleNamespace(data="capture", packets=[packet])
    editor._packet_index_by_row_id = {"0": 0}
    editor._packet_hex_row_id = "0"
    editor._packet_hex_original_text = "00 01"
    refreshes = []
    editor._refresh_packets = lambda sequence: refreshes.append(sequence)
    decodes = []
    editor._decode_selected_packet = lambda: decodes.append(True)
    event = types.SimpleNamespace(widget=types.SimpleNamespace(
        get=lambda: "AA BB"))

    editor._on_packet_hex_finished(event)

    assert writes == [("capture", b"\xaa\xbb")]
    assert refreshes == [4]
    assert decodes == [True]


def test_packet_tree_nests_fragment_breakdown():
    """The packet tree should correctly nest fragment breakdowns."""

    class TreeRecorder:
        """A simple tree recorder to track inserted rows and readonly cells."""

        def __init__(self):
            """Initialize the tree recorder."""
            self.rows = []
            self.readonly_cells = []

        def get_children(self):
            """Return the children of the current tree node."""
            return ()

        def delete(self, *_row_ids):
            """Delete the specified rows from the tree."""
            pass

        def insert(self, parent, _position, **options):
            """Insert a new row into the tree."""
            self.rows.append((parent, options))

        def set_readonly_cell(self, cell, readonly):
            """Mark a cell as readonly or editable."""
            self.readonly_cells.append((cell, readonly))

        def selection_set(self, _row_id):
            """Select the specified row in the tree."""
            pass

    editor = object.__new__(PacketDataEditorWindow)
    editor.tree = TreeRecorder()
    editor.status_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor.capture_file = Path("capture.pcap")
    editor.document = types.SimpleNamespace(
        data=bytearray.fromhex("AABBCCDD"),
        packets=[
            types.SimpleNamespace(
                sequence=0,
                timestamps={"timestamp": "2026-09-13 10:00:00.000000123"},
                ip_version=4,
                source="192.0.2.1",
                destination="198.51.100.2",
                protocol=17,
                identification=0x1234,
                data=bytearray.fromhex("AABBCCDD"),
                complete=True,
                fragments=[
                    types.SimpleNamespace(sequence=1,
                                          timestamps={"timestamp": "first"},
                                          capture_offset=0,
                                          payload_offset=0,
                                          length=2,
                                          more_fragments=True),
                    types.SimpleNamespace(sequence=3,
                                          timestamps={"timestamp": "second"},
                                          capture_offset=2,
                                          payload_offset=2,
                                          length=2,
                                          more_fragments=False),
                ],
            )
        ],
    )

    editor._refresh_packets(None)

    assert [parent for parent, _options in editor.tree.rows] == ["", "0", "0"]
    assert editor.tree.rows[1][1]["text"] == "Fragment"
    assert editor.tree.rows[0][1]["values"][1] == (
        "2026-09-13 10:00:00.000000123")
    first_values = editor.tree.rows[1][1]["values"]
    second_values = editor.tree.rows[2][1]["values"]
    assert first_values == (2, "first", "", "", "", "", "", 2, "Offset 0",
                            "AA BB")
    assert second_values == (4, "second", "", "", "", "", "", 2, "Offset 2",
                             "CC DD")
    assert editor._packet_index_by_row_id["0:fragment:1"] == 0
    assert (("0:fragment:1", PacketDataEditorWindow.PACKET_HEX_COLUMN_ID),
            True) in editor.tree.readonly_cells


def test_packet_tree_hides_single_fragment_breakdown():
    """A packet with one fragment should not show a redundant child row."""

    class TreeRecorder:
        """A simple tree recorder to track inserted rows and readonly cells."""

        def __init__(self):
            self.rows = []

        def get_children(self):
            """Return the children of the current tree node."""
            return ()

        def delete(self, *_row_ids):
            """Delete the specified rows from the tree."""
            pass

        def insert(self, parent, _position, **options):
            """Insert a new row into the tree."""
            self.rows.append((parent, options))

        def set_readonly_cell(self, _cell, _readonly):
            """Mark a cell as readonly or editable."""
            pass

        def selection_set(self, _row_id):
            """Select the specified row in the tree."""
            pass

    editor = object.__new__(PacketDataEditorWindow)
    editor.tree = TreeRecorder()
    editor.status_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor.capture_file = Path("capture.pcap")
    editor.document = types.SimpleNamespace(
        data=bytearray.fromhex("AABB"),
        packets=[
            types.SimpleNamespace(
                sequence=0,
                timestamps={},
                ip_version=4,
                source="192.0.2.1",
                destination="198.51.100.2",
                protocol=17,
                identification=0x1234,
                data=bytearray.fromhex("AABB"),
                complete=True,
                fragments=[
                    types.SimpleNamespace(sequence=0,
                                          timestamps={},
                                          capture_offset=0,
                                          payload_offset=0,
                                          length=2),
                ],
            )
        ],
    )

    editor._refresh_packets(None)

    assert [parent for parent, _options in editor.tree.rows] == [""]


def test_struct_value_edit_encodes_and_writes_back_in_this_window(monkeypatch):
    """Test that editing a struct value correctly encodes
       and writes back the data."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(sequence=2, data="packet-data")
    writes = []
    packet.replace_data = lambda capture, data: writes.append((capture, data))
    editor.document = types.SimpleNamespace(data="capture")
    editor.struct_instance = "old-instance"
    editor.struct_layout = types.SimpleNamespace(type_dict="types")
    editor._detail_value_row_id = "field"
    editor._detail_value_original_text = "1"
    editor._lua_plugin_manager = types.SimpleNamespace(
        apply_encode=lambda instance: f"plugin:{instance}",
        apply_decode=lambda instance: f"plugin:{instance}",
    )
    editor._detail_path_by_row_id = {"field": (0, )}
    editor._selected_packet = lambda: packet
    editor._refresh_packets = lambda _sequence: None
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(packet_editor_module, "replace_instance_value",
                        lambda *_args: "updated-instance")
    encoded_instances = []
    monkeypatch.setattr(
        packet_editor_module,
        "encode",
        lambda _layout, instance, _data: encoded_instances.append(instance) or
        bytearray(b"encoded"),
    )
    monkeypatch.setattr(packet_editor_module, "decode",
                        lambda *_args: "decoded-instance")
    event = types.SimpleNamespace(widget=types.SimpleNamespace(get=lambda: "2"))

    editor._on_detail_value_finished(event)

    assert writes == [("capture", b"encoded")]
    assert encoded_instances == ["plugin:updated-instance"]
    assert editor.struct_instance == "plugin:decoded-instance"


def test_selected_packet_uses_matching_payload_layout(monkeypatch):
    """Test that the selected packet uses the matching payload layout."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(complete=True, data=b"payload")
    layout = types.SimpleNamespace(struct_def_name="udp")
    editor.payload_struct_defs = ["definition"]
    editor._lua_plugin_manager = types.SimpleNamespace(
        apply_decode=lambda instance: f"plugin:{instance}")
    editor._selected_packet = lambda: packet
    labels = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **values: labels.append(values["text"]))
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(packet_editor_module, "matching_struct_layout",
                        lambda definitions, selected: layout)
    monkeypatch.setattr(packet_editor_module, "decode",
                        lambda selected_layout, data: "decoded")

    editor._decode_selected_packet()

    assert editor.struct_layout is layout
    assert editor.struct_instance == "plugin:decoded"
    assert labels == ["Payload: udp"]


def test_unmatched_packet_is_hex_only(monkeypatch):
    """Test that a packet with no matching layout is displayed as hex only."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(complete=True, data=b"payload")
    editor.payload_struct_defs = ["definition"]
    editor._selected_packet = lambda: packet
    labels = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **values: labels.append(values["text"]))
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(packet_editor_module, "matching_struct_layout",
                        lambda definitions, selected: None)

    editor._decode_selected_packet()

    assert editor.struct_layout is None
    assert editor.struct_instance is None
    assert labels == ["Payload: Hex only"]
