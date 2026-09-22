"""Tests for direct and package loading of the packet data editor."""
# pylint: disable=protected-access,unnecessary-lambda,unnecessary-pass
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


def test_payload_struct_dir_falls_back_to_packet_data_dir(tmp_path):
    """Payload Struct dialogs use data_dir until their own setting exists."""
    settings_file = tmp_path / "setting.json"
    settings_file.write_text(
        json.dumps({"PacketDataEditor": {
            "data_dir": "capture-dir"
        }}),
        encoding="utf-8",
    )
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path

    assert editor._load_payload_struct_dir_setting() == Path("capture-dir")


def test_payload_struct_dir_setting_overrides_packet_data_dir(tmp_path):
    """The dedicated Payload Struct directory takes precedence."""
    settings_file = tmp_path / "setting.json"
    settings_file.write_text(
        json.dumps({
            "PacketDataEditor": {
                "data_dir": "capture-dir",
                "last_payload_struct_dir": "payload-dir",
            }
        }),
        encoding="utf-8",
    )
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path

    assert editor._load_payload_struct_dir_setting() == Path("payload-dir")


def test_payload_struct_editor_remembers_its_last_directory(
        monkeypatch, tmp_path):
    """Closing the Payload Struct editor stores its last selected directory."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = tmp_path / "captures"
    editor.last_payload_struct_dir = tmp_path / "initial-payloads"
    editor.payload_struct_defs = []
    editor._decode_selected_packet = lambda: None
    opened = []
    selected_dir = tmp_path / "selected-payloads"

    class DummyPayloadStructDefEditor:

        def __init__(self, parent, definitions, *, data_dir):
            opened.append((parent, definitions, data_dir))
            self.data_dir = selected_dir

    module = types.SimpleNamespace(
        PayloadStructDefEditor=DummyPayloadStructDefEditor)
    monkeypatch.setattr(packet_editor_module, "import_module",
                        lambda _name: module)
    monkeypatch.setattr(packet_editor_module, "show_modal_window",
                        lambda _parent, _editor: None)

    editor._open_payload_struct_def_editor()

    settings = json.loads(
        (tmp_path / "setting.json").read_text(encoding="utf-8"))
    assert opened == [(editor, editor.payload_struct_defs,
                       tmp_path / "initial-payloads")]
    assert editor.data_dir == tmp_path / "captures"
    assert editor.last_payload_struct_dir == selected_dir
    assert settings["PacketDataEditor"]["last_payload_struct_dir"] == (
        selected_dir.as_posix())


def test_open_capture_applies_decode_plugin(monkeypatch, tmp_path):
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path
    editor.data_dir = Path(".")
    editor._lua_plugin_manager = types.SimpleNamespace(
        apply_decode=lambda instance: f"plugin:{instance}")
    editor._refresh_packets = lambda *_args: None
    progress_titles = []
    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda _parent, title, worker:
        (progress_titles.append(title) or worker(lambda _progress: None)),
    )
    opened = []
    document = types.SimpleNamespace()

    def open_capture(path, decode_transform, *, progress_callback):
        opened.append((path, decode_transform("capture-instance")))
        progress_callback(1.0)
        return document

    monkeypatch.setattr(packet_editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "capture.pcap")
    monkeypatch.setattr(packet_editor_module.CaptureDocument, "open",
                        open_capture)

    editor._open_capture()

    assert opened == [("capture.pcap", "plugin:capture-instance")]
    assert editor.document is document
    assert progress_titles == ["Decoding and reassembling capture..."]


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
    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda _parent, _title, worker: worker(lambda _progress: None),
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
                        lambda *_args, **_kwargs: "decoded-instance")
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
    progress_titles = []
    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda _parent, title, worker:
        (progress_titles.append(title) or worker(lambda _progress: None)),
    )
    editor._selected_packet = lambda: packet
    labels = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **values: labels.append(values["text"]))
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(packet_editor_module, "matching_struct_layout",
                        lambda definitions, selected: layout)
    decode_calls = []

    def decode_packet(selected_layout, data, *, progress_callback):
        decode_calls.append((selected_layout, data))
        progress_callback(1.0)
        return "decoded"

    monkeypatch.setattr(packet_editor_module, "decode", decode_packet)

    editor._decode_selected_packet()

    assert editor.struct_layout is layout
    assert editor.struct_instance == "plugin:decoded"
    assert labels == ["Payload: udp"]
    assert decode_calls == [(layout, b"payload")]
    assert progress_titles == ["Decoding packet..."]


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


def test_unmatched_packet_detail_is_grouped_by_bytes_per_row():
    """Raw payload rows use the selected byte count."""

    class DetailTreeRecorder:

        def __init__(self):
            self.rows = []
            self.readonly = {}

        def get_children(self):
            return ()

        def delete(self, *_row_ids):
            pass

        def insert(self, parent, _position, **options):
            self.rows.append((parent, options))

        def set_readonly_column(self, column_id, readonly=True):
            self.readonly[column_id] = readonly

    editor = object.__new__(PacketDataEditorWindow)
    editor.detail_tree = DetailTreeRecorder()
    editor.bytes_per_row_combo = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor.bytes_per_row = 4
    editor.struct_instance = None
    editor._selected_packet = lambda: types.SimpleNamespace(
        complete=True,
        data=bytes.fromhex("001122334455"),
    )

    editor._refresh_detail_tree()

    assert [options["iid"] for _parent, options in editor.detail_tree.rows
            ] == ["raw-0", "raw-4"]
    assert [options["values"]
            for _parent, options in editor.detail_tree.rows] == [
                ("0,0", "", "", "", "4,0", "00 11 22 33"),
                ("4,0", "", "", "", "2,0", "44 55"),
            ]
    assert editor.detail_tree.readonly["#4"] is True
    assert editor.detail_tree.readonly["#6"] is False


def test_raw_detail_hex_edit_writes_back_to_packet():
    """Editing a raw payload row replaces the selected packet data."""
    editor = object.__new__(PacketDataEditorWindow)
    writes = []
    packet = types.SimpleNamespace(
        sequence=3,
        complete=True,
        data=bytes.fromhex("001122334455"),
        replace_data=lambda capture, data: writes.append((capture, data)),
    )
    editor.document = types.SimpleNamespace(data="capture")
    editor.struct_instance = None
    editor.bytes_per_row = 4
    editor._detail_raw_row_id = "raw-0"
    editor._detail_raw_original_text = "00 11 22 33"
    editor._selected_packet = lambda: packet
    refreshes = []
    editor._refresh_packets = lambda sequence: refreshes.append(sequence)
    editor._decode_selected_packet = lambda: None
    event = types.SimpleNamespace(widget=types.SimpleNamespace(
        get=lambda: "AA BB CC DD"))

    editor._on_detail_raw_hex_finished(event)

    assert writes == [("capture", bytes.fromhex("AABBCCDD4455"))]
    assert refreshes == [3]


def test_bytes_per_row_change_refreshes_only_raw_detail():
    """Changing row size rebuilds the lower pane only in raw mode."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.bytes_per_row = 4
    editor.bytes_per_row_combo = types.SimpleNamespace(get=lambda: "8")
    refreshes = []
    editor._refresh_detail_tree = lambda: refreshes.append(True)
    editor.struct_instance = None

    editor._on_bytes_per_row_changed(types.SimpleNamespace())

    assert editor.bytes_per_row == 8
    assert refreshes == [True]


def test_run_with_progress_is_called_directly(monkeypatch):
    """Progress work uses the editor as the shared dialog parent."""
    editor = object.__new__(PacketDataEditorWindow)
    worker = object()
    calls = []
    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda parent, title, callback: calls.append(
            (parent, title, callback)) or "result",
    )

    result = packet_editor_module.run_with_progress(editor, "Working", worker)

    assert result == "result"
    assert calls == [(editor, "Working", worker)]


def test_open_capture_cancel_does_nothing(monkeypatch, tmp_path):
    """Canceling the open dialog leaves the current document untouched."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.data_dir = tmp_path
    editor.document = "current"
    monkeypatch.setattr(packet_editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "")

    editor._open_capture()

    assert editor.document == "current"


def test_open_capture_handles_cancel_and_decode_errors(monkeypatch, tmp_path):
    """Canceled and failed capture processing do not replace the document."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.data_dir = tmp_path
    editor.document = "current"
    monkeypatch.setattr(packet_editor_module.filedialog, "askopenfilename",
                        lambda **_kwargs: "capture.pcap")
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))

    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda *_args:
        (_ for _ in ()).throw(packet_editor_module.OperationCanceledError()),
    )
    editor._open_capture()
    assert editor.document == "current"
    assert errors == []

    monkeypatch.setattr(
        packet_editor_module,
        "run_with_progress",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad capture")),
    )
    editor._open_capture()
    assert editor.document == "current"
    assert errors[0][0] == ("Open Error", "bad capture")
    assert errors[0][1]["parent"] is editor


def test_selected_packet_handles_empty_and_unknown_selections():
    """Packet lookup returns None until a known packet row is selected."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.document = None
    assert editor._selected_packet() is None

    selections = [(), ("unknown", ), ("packet", )]
    editor.tree = types.SimpleNamespace(selection=lambda: selections.pop(0))
    packet = object()
    editor.document = types.SimpleNamespace(packets=[packet])
    editor._packet_index_by_row_id = {"packet": 0}

    assert editor._selected_packet() is None
    assert editor._selected_packet() is None
    assert editor._selected_packet() is packet


def test_save_capture_uses_existing_path_or_save_as():
    """Save routes to Save As only when no capture path exists."""
    editor = object.__new__(PacketDataEditorWindow)
    calls = []
    editor._save_capture_as = lambda: calls.append("save-as")
    editor._write_capture = lambda path: calls.append(path)

    editor.capture_file = None
    editor._save_capture()
    editor.capture_file = Path("capture.pcap")
    editor._save_capture()

    assert calls == ["save-as", Path("capture.pcap")]


def test_save_capture_as_validates_document_and_dialog(monkeypatch, tmp_path):
    """Save As validates state, cancellation, and a chosen path."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.data_dir = tmp_path
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))
    editor.document = None
    editor._save_capture_as()
    assert errors[0][0] == ("No Capture", "Open a capture file first.")

    writes = []
    editor.document = types.SimpleNamespace(capture_format="pcapng")
    editor._write_capture = writes.append
    paths = ["", str(tmp_path / "saved.pcapng")]
    dialog_options = []

    def choose_path(**kwargs):
        dialog_options.append(kwargs)
        return paths.pop(0)

    monkeypatch.setattr(packet_editor_module.filedialog, "asksaveasfilename",
                        choose_path)
    editor._save_capture_as()
    editor._save_capture_as()

    assert writes == [tmp_path / "saved.pcapng"]
    assert dialog_options[0]["defaultextension"] == ".pcapng"
    assert dialog_options[0]["initialdir"] == tmp_path


def test_write_capture_handles_missing_document_and_save_error(
        monkeypatch, tmp_path):
    """Write errors are reported without changing the current capture path."""
    editor = object.__new__(PacketDataEditorWindow)
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))
    editor.document = None
    editor._write_capture(tmp_path / "missing.pcap")
    assert errors[-1][0][0] == "No Capture"

    editor.capture_file = Path("current.pcap")
    editor.document = types.SimpleNamespace(
        save=lambda _path: (_ for _ in ()).throw(OSError("disk full")))
    editor._write_capture(tmp_path / "failed.pcap")

    assert errors[-1][0] == ("Save Error", "disk full")
    assert editor.capture_file == Path("current.pcap")


def test_write_capture_updates_path_setting_and_reports_success(
        monkeypatch, tmp_path):
    """A successful save updates the active path and remembered directory."""
    editor = object.__new__(PacketDataEditorWindow)
    saved = []
    editor.document = types.SimpleNamespace(save=saved.append)
    remembered = []
    editor._remember_data_dir = remembered.append
    messages = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showinfo",
                        lambda *args, **kwargs: messages.append((args, kwargs)))
    path = tmp_path / "saved.pcap"

    editor._write_capture(path)

    assert saved == [path]
    assert editor.capture_file == path
    assert remembered == [path]
    assert messages == [(('Saved', f'Saved to:\n{path}'), {'parent': editor})]


def test_path_settings_handle_missing_and_malformed_files(tmp_path):
    """Missing or malformed settings behave as if no path was stored."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path

    assert editor._load_dir_setting() is None

    settings_file = tmp_path / "setting.json"
    settings_file.write_text("not json", encoding="utf-8")
    assert editor._load_dir_setting() is None

    settings_file.write_text("[]", encoding="utf-8")
    assert editor._load_dir_setting() is None


def test_remember_path_recovers_from_malformed_settings(tmp_path):
    """Remembering a path replaces malformed settings with valid JSON."""
    settings_file = tmp_path / "setting.json"
    settings_file.write_text("not json", encoding="utf-8")
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path

    editor._remember_payload_struct_dir(tmp_path / "layouts")

    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    assert settings == {
        "PacketDataEditor": {
            "last_payload_struct_dir": (tmp_path / "layouts").as_posix(),
        }
    }


def test_remember_path_ignores_write_errors(monkeypatch, tmp_path):
    """An unwritable settings file does not break editor interaction."""
    editor = object.__new__(PacketDataEditorWindow)
    editor.apl_dir = tmp_path
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
    )

    editor._remember_path_setting("data_dir", tmp_path)


def test_packet_selection_event_requests_decode():
    """Selecting a packet requests a refresh of decoded details."""
    editor = object.__new__(PacketDataEditorWindow)
    calls = []
    editor._decode_selected_packet = lambda: calls.append(True)

    editor._on_packet_selected(None)

    assert calls == [True]


def test_decode_selected_packet_handles_absent_and_incomplete_packets():
    """Absent and incomplete packets remain in hex-only mode."""
    editor = object.__new__(PacketDataEditorWindow)
    packets = [None, types.SimpleNamespace(complete=False)]
    editor._selected_packet = lambda: packets.pop(0)
    editor.payload_struct_defs = []
    labels = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **values: labels.append(values["text"]))
    refreshes = []
    editor._refresh_detail_tree = lambda: refreshes.append(True)

    editor._decode_selected_packet()
    editor._decode_selected_packet()

    assert labels == ["Payload: Hex only", "Payload: Hex only"]
    assert refreshes == [True, True]


def test_decode_selected_packet_handles_cancel_and_error(monkeypatch):
    """Canceled decoding is silent and malformed layouts are reported."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(complete=True, data=b"payload")
    layout = types.SimpleNamespace(struct_def_name="layout")
    editor._selected_packet = lambda: packet
    editor.payload_struct_defs = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(packet_editor_module, "matching_struct_layout",
                        lambda *_args: layout)
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))

    editor._decode_with_progress = lambda *_args: (_ for _ in ()).throw(
        packet_editor_module.OperationCanceledError())
    editor._decode_selected_packet()
    assert errors == []

    editor._decode_with_progress = lambda *_args: (_ for _ in ()).throw(
        ValueError("bad layout"))
    editor._decode_selected_packet()
    assert errors[0][0] == ("Decode Error", "bad layout")
    assert errors[0][1]["parent"] is editor


def test_decode_selected_packet_reports_condition_attribute_error(monkeypatch):
    """A malformed condition (e.g. `protocol.UDP`) is reported, not silent."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(complete=True, data=b"payload")
    editor._selected_packet = lambda: packet
    editor.payload_struct_defs = []
    editor.definition_label = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor._refresh_detail_tree = lambda: None
    monkeypatch.setattr(
        packet_editor_module, "matching_struct_layout", lambda *_args:
        (_ for _ in
         ()).throw(AttributeError("'int' object has no attribute 'UDP'")))
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))

    editor._decode_selected_packet()

    assert errors[0][0] == ("Decode Error",
                            "'int' object has no attribute 'UDP'")
    assert errors[0][1]["parent"] is editor


def test_detail_edit_start_only_tracks_value_column():
    """Only the editable detail value cell starts value tracking."""
    editor = object.__new__(PacketDataEditorWindow)
    editor._detail_value_row_id = None
    editor._detail_value_original_text = ""
    editor.detail_tree = types.SimpleNamespace(
        get_cell_value=lambda cell: f"value:{cell[0]}")

    editor._on_detail_edit_started(("row", "#1"))
    assert editor._detail_value_row_id is None

    editor._on_detail_edit_started(("row", editor.DETAIL_VALUE_COLUMN_ID))
    assert editor._detail_value_row_id == "row"
    assert editor._detail_value_original_text == "value:row"


def test_detail_value_finish_ignores_incomplete_or_unchanged_edits():
    """Incomplete editor state and unchanged text produce no write-back."""
    editor = object.__new__(PacketDataEditorWindow)
    editor._detail_value_row_id = None
    editor._selected_packet = lambda: None
    editor.struct_instance = None
    editor.struct_layout = None
    editor.document = None
    event = types.SimpleNamespace(widget=types.SimpleNamespace(get=lambda: "1"))

    editor._on_detail_value_finished(event)

    editor._detail_value_row_id = "row"
    editor._selected_packet = lambda: object()
    editor.struct_instance = object()
    editor.struct_layout = object()
    editor.document = object()
    editor._detail_value_original_text = "1"
    editor._on_detail_value_finished(event)

    assert editor._detail_value_row_id is None


def test_detail_value_finish_handles_cancel_and_value_error(monkeypatch):
    """Canceled and invalid detail edits do not refresh corrupted state."""
    editor = object.__new__(PacketDataEditorWindow)
    packet = types.SimpleNamespace(sequence=3)
    editor._selected_packet = lambda: packet
    editor.struct_instance = object()
    editor.struct_layout = types.SimpleNamespace(type_dict={})
    editor.document = object()
    editor._detail_path_by_row_id = {"row": (0, )}
    editor._detail_value_original_text = "old"
    refreshes = []
    editor._refresh_packets = lambda sequence: refreshes.append(sequence)
    editor._refresh_detail_tree = lambda: refreshes.append("detail")
    event = types.SimpleNamespace(widget=types.SimpleNamespace(
        get=lambda: "new"))
    errors = []
    monkeypatch.setattr(packet_editor_module.messagebox, "showerror",
                        lambda *args, **kwargs: errors.append((args, kwargs)))

    editor._detail_value_row_id = "row"
    monkeypatch.setattr(
        packet_editor_module,
        "replace_instance_value",
        lambda *_args:
        (_ for _ in ()).throw(packet_editor_module.OperationCanceledError()),
    )
    editor._on_detail_value_finished(event)
    assert refreshes == []
    assert errors == []

    editor._detail_value_row_id = "row"
    monkeypatch.setattr(
        packet_editor_module,
        "replace_instance_value",
        lambda *_args: (_ for _ in ()).throw(ValueError("invalid value")),
    )
    editor._on_detail_value_finished(event)

    assert errors[0][0] == ("Value Error", "invalid value")
    assert refreshes == [3, "detail"]


def test_refresh_detail_tree_clears_and_inserts_current_instance(monkeypatch):
    """Refreshing details clears old rows and inserts the current instance."""
    editor = object.__new__(PacketDataEditorWindow)
    deleted = []
    editor.detail_tree = types.SimpleNamespace(
        get_children=lambda: ("old-1", "old-2"),
        delete=lambda *rows: deleted.append(rows),
        set_readonly_column=lambda *_args, **_kwargs: None,
    )
    editor.bytes_per_row_combo = types.SimpleNamespace(
        configure=lambda **_kwargs: None)
    editor._selected_packet = lambda: None
    inserted = []
    editor._insert_instance = lambda *args: inserted.append(args)
    monkeypatch.setattr(packet_editor_module, "InfoSize", lambda: "zero")

    editor.struct_instance = None
    editor._refresh_detail_tree()
    editor.struct_instance = "instance"
    editor._refresh_detail_tree()

    assert deleted == [("old-1", "old-2"), ("old-1", "old-2")]
    assert inserted == [("instance", "", "zero")]
    assert editor._detail_path_by_row_id == {}


def test_insert_instance_builds_nested_rows_and_paths(monkeypatch):
    """Nested struct fields are displayed recursively with stable paths."""

    class DetailTreeRecorder:

        def __init__(self):
            self.rows = []
            self.readonly = []

        def insert(self, parent, _position, **options):
            row_id = f"row-{len(self.rows)}"
            self.rows.append((row_id, parent, options))
            return row_id

        def set_readonly_cell(self, cell, readonly):
            self.readonly.append((cell, readonly))

    def field(name, offset, value):
        definition = types.SimpleNamespace(name=name,
                                           offset=offset,
                                           size=1,
                                           type=f"type:{name}")
        return types.SimpleNamespace(field_def=definition, value=value)

    nested = types.SimpleNamespace(field_instances=[field("inner", 1, 9)])
    instance = types.SimpleNamespace(field_instances=[
        field("group", 2, nested),
        field("plain", 4, 5),
    ])
    editor = object.__new__(PacketDataEditorWindow)
    editor.detail_tree = DetailTreeRecorder()
    editor.struct_layout = types.SimpleNamespace(
        type_dict=types.SimpleNamespace(enum_dict={}))
    editor._detail_path_by_row_id = {}
    editor._selected_packet = lambda: types.SimpleNamespace(data=b"packet")
    monkeypatch.setattr(packet_editor_module, "bits_get",
                        lambda *_args: types.SimpleNamespace(to_bytes=b"\xab"))
    monkeypatch.setattr(packet_editor_module, "format_infosize", str)
    monkeypatch.setattr(packet_editor_module, "format_type", str)
    monkeypatch.setattr(
        packet_editor_module, "format_field_value",
        lambda field_instance, _type_dict: str(field_instance.value))

    editor._insert_instance(instance, "", 10)

    assert [row[1] for row in editor.detail_tree.rows] == ["", "row-0", ""]
    assert editor._detail_path_by_row_id == {
        "row-0": (0, ),
        "row-1": (0, 0),
        "row-2": (1, ),
    }
    assert editor.detail_tree.rows[0][2]["values"][-1] == "AB"
    assert editor.detail_tree.readonly == [
        (("row-0", editor.DETAIL_VALUE_COLUMN_ID), True)
    ]


def test_insert_instance_without_selected_packet_does_nothing():
    """Detail insertion is skipped when no packet is selected."""
    editor = object.__new__(PacketDataEditorWindow)
    editor._selected_packet = lambda: None
    editor.detail_tree = types.SimpleNamespace(
        insert=lambda *_args, **_kwargs:
        (_ for _ in ()).throw(AssertionError("unexpected insert")))

    editor._insert_instance(types.SimpleNamespace(field_instances=[]), "", 0)


def test_refresh_packets_handles_no_document():
    """Refreshing before a capture is loaded only clears stale packet rows."""
    deleted = []
    editor = object.__new__(PacketDataEditorWindow)
    editor.tree = types.SimpleNamespace(
        get_children=lambda: ("old", ),
        delete=lambda *rows: deleted.append(rows),
    )
    editor.document = None

    editor._refresh_packets()

    assert deleted == [("old", )]
    assert editor._packet_index_by_row_id == {}


def test_refresh_packets_marks_incomplete_packet_and_restores_selection():
    """Incomplete packets are labeled and requested selection is restored."""
    rows = []
    selections = []
    statuses = []
    editor = object.__new__(PacketDataEditorWindow)
    editor.tree = types.SimpleNamespace(
        get_children=lambda: (),
        delete=lambda *_rows: None,
        insert=lambda parent, _position, **options: rows.append(
            (parent, options)),
        selection_set=selections.append,
    )
    editor.status_label = types.SimpleNamespace(
        configure=lambda **values: statuses.append(values["text"]))
    editor.capture_file = Path("incomplete.pcap")
    packet = types.SimpleNamespace(
        sequence=5,
        timestamps={},
        ip_version=6,
        source="::1",
        destination="::2",
        protocol=99,
        identification=None,
        data=b"\x01",
        complete=False,
        fragments=[],
    )
    editor.document = types.SimpleNamespace(data=b"", packets=[packet])

    editor._refresh_packets(5)

    values = rows[0][1]["values"]
    assert values[5:9] == ("99", "", 1, "Incomplete")
    assert selections == ["0"]
    assert statuses == ["incomplete.pcap: 1 IP packet(s)"]


def test_nested_treeview_validates_existing_data_columns():
    """Nested rows accept only existing, configured data columns."""

    class TreeStub:

        def exists(self, row_id):
            return row_id == "row"

        def __getitem__(self, key):
            assert key == "columns"
            return ("first", "second")

    tree = TreeStub()
    validate = packet_editor_module._NestedTreeviewEx.is_valid_cell

    assert not validate(tree, ("", "#1"))
    assert not validate(tree, ("missing", "#1"))
    assert not validate(tree, ("row", "invalid"))
    assert not validate(tree, ("row", "#0"))
    assert validate(tree, ("row", "#1"))
    assert validate(tree, ("row", "#2"))
    assert not validate(tree, ("row", "#3"))


def test_nested_treeview_notifies_when_edit_starts(monkeypatch):
    """A successful double click reports the clicked child cell."""
    tree = object.__new__(packet_editor_module._NestedTreeviewEx)
    event = object()
    cell = ("child", "#2")
    monkeypatch.setattr(
        packet_editor_module._NestedTreeviewEx,
        "get_clicked_cell_id_pair",
        lambda _self, received: cell if received is event else None,
    )
    monkeypatch.setattr(packet_editor_module.TreeviewEx, "on_double_click",
                        lambda _self, _event: "break")
    notifications = []
    tree.on_edit_started = notifications.append

    assert tree.on_double_click(event) == "break"
    assert notifications == [cell]

    tree.on_edit_started = None
    monkeypatch.setattr(packet_editor_module.TreeviewEx, "on_double_click",
                        lambda _self, _event: None)
    assert tree.on_double_click(event) is None
    assert notifications == [cell]


def test_window_initialization_sets_paths_state_and_builders(
        monkeypatch, tmp_path):
    """Initialization wires persisted paths, plugin manager, and builders."""
    calls = []
    monkeypatch.setattr(packet_editor_module.tk.Toplevel, "__init__",
                        lambda self, parent: calls.append(("parent", parent)))
    monkeypatch.setattr(PacketDataEditorWindow, "title",
                        lambda self, value: calls.append(("title", value)))
    monkeypatch.setattr(PacketDataEditorWindow, "geometry",
                        lambda self, value: calls.append(("geometry", value)))
    monkeypatch.setattr(PacketDataEditorWindow, "_build_menu",
                        lambda self: calls.append(("menu", self)))
    monkeypatch.setattr(PacketDataEditorWindow, "_build_ui",
                        lambda self: calls.append(("ui", self)))
    monkeypatch.setattr(packet_editor_module, "LuaPluginManager", lambda path:
                        ("plugins", path))
    editor = object.__new__(PacketDataEditorWindow)
    parent = object()

    editor.__init__(parent, apl_dir=tmp_path, data_dir=tmp_path / "data")

    assert editor.apl_dir == tmp_path
    assert editor.data_dir == tmp_path / "data"
    assert editor.last_payload_struct_dir == tmp_path / "data"
    assert editor.capture_file is None
    assert editor.document is None
    assert editor.payload_struct_defs == []
    assert editor._lua_plugin_manager == ("plugins", tmp_path / "plugins")
    assert calls == [
        ("parent", parent),
        ("title", "Packet Data Editor"),
        ("geometry", "1080x620"),
        ("menu", editor),
        ("ui", editor),
    ]


def test_build_menu_wires_commands(monkeypatch):
    """The menu exposes capture, definition, and exit commands."""

    class MenuRecorder:

        instances = []

        def __init__(self, parent, **options):
            self.parent = parent
            self.options = options
            self.commands = []
            self.cascades = []
            type(self).instances.append(self)

        def add_command(self, **options):
            self.commands.append(options)

        def add_separator(self):
            self.commands.append({"separator": True})

        def add_cascade(self, **options):
            self.cascades.append(options)

    editor = object.__new__(PacketDataEditorWindow)
    configured = []
    editor.config = lambda **options: configured.append(options)
    monkeypatch.setattr(packet_editor_module.tk, "Menu", MenuRecorder)

    editor._build_menu()

    assert len(MenuRecorder.instances) == 3
    menubar = MenuRecorder.instances[0]
    file_menu = MenuRecorder.instances[1]
    definition_menu = MenuRecorder.instances[2]
    assert [item.get("label") for item in file_menu.commands] == [
        "Open Capture...",
        None,
        "Save Capture",
        "Save Capture As...",
        None,
        "Exit",
    ]
    assert definition_menu.commands[0]["label"] == (
        "Payload Struct Definitions...")
    assert [item["label"]
            for item in menubar.cascades] == ["File", "Packet Definition"]
    assert configured == [{"menu": menubar}]


def test_build_ui_configures_trees_and_edit_bindings(monkeypatch):
    """UI construction configures both trees and their edit callbacks."""

    class WidgetRecorder:

        instances = []

        def __init__(self, parent=None, **options):
            self.parent = parent
            self.options = options
            self.calls = []
            self.entry = types.SimpleNamespace(bind=self._entry_bind)
            self.on_edit_started = None
            type(self).instances.append(self)

        def _entry_bind(self, *args, **kwargs):
            self.calls.append(("entry_bind", args, kwargs))

        def configure(self, *args, **kwargs):
            self.calls.append(("configure", args, kwargs))

        def set(self, value):
            self.calls.append(("set", (value, ), {}))

        def pack(self, *args, **kwargs):
            self.calls.append(("pack", args, kwargs))

        def add(self, *args, **kwargs):
            self.calls.append(("add", args, kwargs))

        def heading(self, *args, **kwargs):
            self.calls.append(("heading", args, kwargs))

        def column(self, *args, **kwargs):
            self.calls.append(("column", args, kwargs))

        def set_readonly_column(self, *args, **kwargs):
            self.calls.append(("readonly", args, kwargs))

        def bind(self, *args, **kwargs):
            self.calls.append(("bind", args, kwargs))

    class StyleRecorder:

        def __init__(self, parent):
            self.parent = parent

        def configure(self, *args, **kwargs):
            style_calls.append((args, kwargs))

    style_calls = []
    monkeypatch.setattr(packet_editor_module.ttk, "Style", StyleRecorder)
    monkeypatch.setattr(packet_editor_module.ttk, "Label", WidgetRecorder)
    monkeypatch.setattr(packet_editor_module.ttk, "Frame", WidgetRecorder)
    monkeypatch.setattr(packet_editor_module.ttk, "Combobox", WidgetRecorder)
    monkeypatch.setattr(packet_editor_module.ttk, "Panedwindow", WidgetRecorder)
    monkeypatch.setattr(packet_editor_module.ttk, "Labelframe", WidgetRecorder)
    monkeypatch.setattr(packet_editor_module, "_NestedTreeviewEx",
                        WidgetRecorder)
    editor = object.__new__(PacketDataEditorWindow)
    editor.bytes_per_row = 4

    editor._build_ui()

    assert style_calls == [(('PacketData.Treeview', ), {"font": "TkFixedFont"})]
    packet_readonly = [
        call[1][0] for call in editor.tree.calls if call[0] == "readonly"
    ]
    detail_readonly = [
        call[1][0] for call in editor.detail_tree.calls if call[0] == "readonly"
    ]
    assert packet_readonly == [f"#{index}" for index in range(1, 11)]
    assert detail_readonly == ["#1", "#2", "#3", "#5", "#4", "#6"]
    assert editor.tree.on_edit_started is None
    assert editor.detail_tree.on_edit_started.__self__ is editor
    assert editor.detail_tree.on_edit_started.__func__ is (
        PacketDataEditorWindow._on_detail_edit_started)
    assert any(call[0] == "bind" and call[1][0] == "<<TreeviewSelect>>"
               for call in editor.tree.calls)


def test_main_wires_window_close_and_event_loop(monkeypatch):
    """The standalone entry point owns closing and starts Tk's event loop."""
    calls = []

    class RootStub:

        def withdraw(self):
            calls.append("withdraw")

        def destroy(self):
            calls.append("destroy")

        def mainloop(self):
            calls.append("mainloop")

    class EditorStub:

        def __init__(self, parent):
            calls.append(("editor", parent))

        def protocol(self, name, callback):
            calls.append(("protocol", name, callback))

    root = RootStub()
    monkeypatch.setattr(packet_editor_module.tk, "Tk", lambda: root)
    monkeypatch.setattr(packet_editor_module, "PacketDataEditorWindow",
                        EditorStub)

    packet_editor_module.main()

    assert calls[:2] == ["withdraw", ("editor", root)]
    assert calls[2][0:2] == ("protocol", "WM_DELETE_WINDOW")
    calls[2][2]()
    assert calls[-2:] == ["mainloop", "destroy"]
