"""Editor for reassembled IP packet data in PCAP and PCAPNG files."""
from __future__ import annotations

import json
import tkinter as tk
from importlib import import_module
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from sltcodec import StructLayout, decode, encode
from sltcore import InfoSize, bits_get
from tkinterex import show_modal_window
from treeviewex import TreeviewEx

from sltgui._progress_dialog import OperationCanceledError, run_with_progress

if TYPE_CHECKING:
    from ._infosize_utils import format_infosize
    from ._packet_data_model import CaptureDocument, ReassembledPacket
    from ._payload_struct_defs import matching_struct_layout
    from ._struct_instance_model import (format_type, format_value,
                                         replace_instance_value)
    from .lua_plugins import NO_LUA_PLUGINS, LuaPluginManager
elif __package__:
    packet_model = import_module("._packet_data_model", __package__)
    CaptureDocument = packet_model.CaptureDocument
    ReassembledPacket = packet_model.ReassembledPacket
    payload_defs_module = import_module("._payload_struct_defs", __package__)
    matching_struct_layout = payload_defs_module.matching_struct_layout
    format_infosize = import_module("._infosize_utils",
                                    __package__).format_infosize
    instance_model = import_module("._struct_instance_model", __package__)
    format_type = instance_model.format_type
    format_value = instance_model.format_value
    replace_instance_value = instance_model.replace_instance_value
    lua_plugins_module = import_module(".lua_plugins", __package__)
    LuaPluginManager = lua_plugins_module.LuaPluginManager
    NO_LUA_PLUGINS = lua_plugins_module.NO_LUA_PLUGINS
else:
    packet_model = import_module("_packet_data_model")
    CaptureDocument = packet_model.CaptureDocument
    ReassembledPacket = packet_model.ReassembledPacket
    payload_defs_module = import_module("_payload_struct_defs")
    matching_struct_layout = payload_defs_module.matching_struct_layout
    format_infosize = import_module("_infosize_utils").format_infosize
    instance_model = import_module("_struct_instance_model")
    format_type = instance_model.format_type
    format_value = instance_model.format_value
    replace_instance_value = instance_model.replace_instance_value
    lua_plugins_module = import_module("lua_plugins")
    LuaPluginManager = lua_plugins_module.LuaPluginManager
    NO_LUA_PLUGINS = lua_plugins_module.NO_LUA_PLUGINS


class _NestedTreeviewEx(TreeviewEx):  # pylint: disable=too-many-ancestors
    """TreeviewEx that permits editing child rows."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the nested treeview."""
        super().__init__(*args, **kwargs)
        self.on_edit_started = None

    def is_valid_cell(self, cell_id_pair: tuple) -> bool:
        """Check if the specified cell is valid."""
        row_id, column_id = cell_id_pair
        if not row_id or not self.exists(row_id):
            return False
        try:
            column_index = int(str(column_id)[1:]) - 1
        except ValueError:
            return False
        return 0 <= column_index < len(self["columns"])

    def on_double_click(self, event: tk.Event) -> str | None:
        """Handle double-click events on the treeview."""
        cell_id_pair = self.get_clicked_cell_id_pair(event)
        result = super().on_double_click(event)
        if result == "break" and self.on_edit_started is not None:
            self.on_edit_started(cell_id_pair)
        return result


class PacketDataEditorWindow(tk.Toplevel):
    """Display and edit reassembled IP payloads from a capture file."""

    SETTINGS_FILENAME = "setting.json"
    SETTINGS_SECTION = "PacketDataEditor"
    DATA_DIR_KEY = "data_dir"
    LAST_PAYLOAD_STRUCT_DIR_KEY = "last_payload_struct_dir"
    COLUMNS = (
        "sequence",
        "timestamp",
        "version",
        "source",
        "destination",
        "protocol",
        "identification",
        "length",
        "status",
        "hex",
    )
    DETAIL_COLUMNS = ("offset", "name", "type", "value", "size", "hex")
    PACKET_HEX_COLUMN_ID = "#10"
    DETAIL_VALUE_COLUMN_ID = "#4"
    PROTOCOL_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP", 58: "ICMPv6"}

    def _run_with_progress(self, title: str, worker_fn):
        """Run background work using the shared progress dialog."""
        return run_with_progress(self, title, worker_fn)

    def _decode_with_progress(
        self,
        struct_layout: StructLayout,
        data: object,
        title: str = "Decoding packet...",
    ) -> object:
        """Decode packet data and apply the configured decode plugin."""
        instance = self._run_with_progress(
            title,
            lambda progress_callback: decode(
                struct_layout,
                data,
                progress_callback=progress_callback,
            ),
        )
        return self._plugin_manager().apply_decode(instance)

    def __init__(
        self,
        parent: tk.Misc,
        *,
        apl_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        """Initialize the packet data editor window."""
        super().__init__(parent)
        self.apl_dir = Path(apl_dir) if apl_dir is not None else Path.cwd()
        self.data_dir = (Path(data_dir) if data_dir is not None else
                         self._load_dir_setting() or Path.cwd())
        self.last_payload_struct_dir = (self._load_payload_struct_dir_setting()
                                        or self.data_dir)
        self.capture_file: Path | None = None
        self.document: CaptureDocument | None = None
        self.payload_struct_defs = []
        self.struct_layout: StructLayout | None = None
        self.struct_instance = None
        self._packet_hex_row_id: str | None = None
        self._packet_hex_original_text = ""
        self._packet_index_by_row_id: dict[str, int] = {}
        self._detail_value_row_id: str | None = None
        self._detail_value_original_text = ""
        self._detail_path_by_row_id: dict[str, tuple[int, ...]] = {}
        self._lua_plugin_manager = LuaPluginManager(self.apl_dir / "plugins")

        self.title("Packet Data Editor")
        self.geometry("1080x620")
        self._build_menu()
        self._build_ui()

    def _build_menu(self) -> None:
        """Build the menu bar for the packet data editor window."""
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open Capture...",
                              command=self._open_capture)
        file_menu.add_separator()
        file_menu.add_command(label="Save Capture", command=self._save_capture)
        file_menu.add_command(label="Save Capture As...",
                              command=self._save_capture_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        definition_menu = tk.Menu(menubar, tearoff=False)
        definition_menu.add_command(
            label="Payload Struct Definitions...",
            command=self._open_payload_struct_def_editor,
        )
        menubar.add_cascade(label="Packet Definition", menu=definition_menu)
        self.config(menu=menubar)

    def _build_ui(self) -> None:
        """Build the main user interface for the packet data editor window."""
        tree_style = "PacketData.Treeview"
        ttk.Style(self).configure(tree_style, font="TkFixedFont")
        self.definition_label = ttk.Label(
            self,
            text="Payload: Hex only",
            padding=(8, 8, 8, 4),
            anchor=tk.E,
        )
        self.definition_label.pack(fill=tk.X)

        panes = ttk.Panedwindow(self, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        packet_frame = ttk.Labelframe(panes, text="Reassembled packets")
        detail_frame = ttk.Labelframe(panes, text="Decoded packet data")
        panes.add(packet_frame, weight=1)
        panes.add(detail_frame, weight=2)

        self.tree = _NestedTreeviewEx(
            packet_frame,
            columns=self.COLUMNS,
            show="tree headings",
            selectmode="browse",
            style=tree_style,
        )
        self.tree.heading("#0", text="Breakdown")
        self.tree.column("#0", width=90, minwidth=70, anchor=tk.W)
        headings = {
            "sequence": "No.",
            "timestamp": "Timestamp",
            "version": "IP",
            "source": "Source",
            "destination": "Destination",
            "protocol": "Protocol",
            "identification": "Identification",
            "length": "Length",
            "status": "Status",
            "hex": "Hex",
        }
        widths = (
            60,
            240,
            50,
            180,
            180,
            90,
            120,
            80,
            100,
            420,
        )
        for column, width in zip(self.COLUMNS, widths, strict=True):
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=width, minwidth=40, anchor=tk.W)
        for column_id in range(1, len(self.COLUMNS)):
            self.tree.set_readonly_column(f"#{column_id}", True)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.on_edit_started = self._on_packet_edit_started
        self.tree.entry.bind("<Return>", self._on_packet_hex_finished, add="+")
        self.tree.entry.bind("<FocusOut>",
                             self._on_packet_hex_finished,
                             add="+")
        self.tree.bind("<<TreeviewSelect>>", self._on_packet_selected)

        self.detail_tree = _NestedTreeviewEx(
            detail_frame,
            columns=self.DETAIL_COLUMNS,
            show="tree headings",
            selectmode="browse",
            style=tree_style,
        )
        self.detail_tree.heading("#0", text="")
        for column in self.DETAIL_COLUMNS:
            self.detail_tree.heading(column, text=column)
        self.detail_tree.column("#0", width=24, stretch=False)
        detail_widths = (100, 180, 140, 260, 80, 320)
        for column, width in zip(self.DETAIL_COLUMNS,
                                 detail_widths,
                                 strict=True):
            self.detail_tree.column(column, width=width, anchor=tk.W)
        for column_id in ("#1", "#2", "#3", "#5", "#6"):
            self.detail_tree.set_readonly_column(column_id, True)
        self.detail_tree.pack(fill=tk.BOTH, expand=True)
        self.detail_tree.on_edit_started = self._on_detail_edit_started
        self.detail_tree.entry.bind("<Return>",
                                    self._on_detail_value_finished,
                                    add="+")
        self.detail_tree.entry.bind("<FocusOut>",
                                    self._on_detail_value_finished,
                                    add="+")

        self.status_label = ttk.Label(self,
                                      text="Open a PCAP or PCAPNG file.",
                                      padding=(8, 0, 8, 8))
        self.status_label.pack(fill=tk.X)

    def _open_capture(self) -> None:
        """Open a capture file and load it into the editor."""
        path = filedialog.askopenfilename(
            title="Open Capture",
            initialdir=self.data_dir,
            filetypes=[
                ("Capture files", "*.pcap *.pcapng"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            document = self._run_with_progress(
                "Decoding and reassembling capture...",
                lambda progress_callback: CaptureDocument.open(
                    path,
                    self._plugin_manager().apply_decode,
                    progress_callback=progress_callback,
                ),
            )
        except OperationCanceledError:
            return
        except (OSError, TypeError, ValueError, NameError, SyntaxError) as exc:
            messagebox.showerror("Open Error", str(exc), parent=self)
            return
        self.capture_file = Path(path)
        self._remember_data_dir(self.capture_file)
        self.document = document
        self._refresh_packets()

    def _settings_file(self) -> Path:
        """Return the path to the settings file for the packet data editor."""
        return self.apl_dir / self.SETTINGS_FILENAME

    def _load_dir_setting(self) -> Path | None:
        """Return the stored Packet Data Editor directory, if any."""
        return self._load_path_setting(self.DATA_DIR_KEY)

    def _load_payload_struct_dir_setting(self) -> Path | None:
        """Return the Payload Struct directory, falling back to data_dir."""
        return (self._load_path_setting(self.LAST_PAYLOAD_STRUCT_DIR_KEY)
                or self._load_dir_setting())

    def _load_path_setting(self, key: str) -> Path | None:
        """Load a directory path from the PacketDataEditor settings."""
        settings_file = self._settings_file()
        if not settings_file.is_file():
            return None
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            directory = settings.get(self.SETTINGS_SECTION, {}).get(key)
        except (OSError, ValueError, AttributeError):
            return None
        return Path(directory) if directory else None

    def _remember_data_dir(self, path: str | Path) -> None:
        """Store the selected capture directory in this editor's section."""
        selected_dir = Path(path).parent
        self.data_dir = selected_dir
        self._remember_path_setting(self.DATA_DIR_KEY, selected_dir)

    def _remember_payload_struct_dir(self, directory: str | Path) -> None:
        """Store the last directory used by the Payload Struct editor."""
        selected_dir = Path(directory)
        self.last_payload_struct_dir = selected_dir
        self._remember_path_setting(self.LAST_PAYLOAD_STRUCT_DIR_KEY,
                                    selected_dir)

    def _remember_path_setting(self, key: str, directory: Path) -> None:
        """Store one PacketDataEditor directory without replacing others."""
        settings_file = self._settings_file()
        settings = {}
        if settings_file.is_file():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                settings = {}
        settings.setdefault(self.SETTINGS_SECTION,
                            {})[key] = directory.as_posix()
        try:
            self.apl_dir.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(settings, indent=2),
                                     encoding="utf-8")
        except OSError:
            pass

    def _open_payload_struct_def_editor(self) -> None:
        """Open the payload structure definition editor."""
        module_name = (f"{__package__}.payload_struct_def_editor"
                       if __package__ else "payload_struct_def_editor")
        editor_class = import_module(module_name).PayloadStructDefEditor
        editor = editor_class(self,
                              self.payload_struct_defs,
                              data_dir=self.last_payload_struct_dir)
        show_modal_window(self, editor)
        self._remember_payload_struct_dir(editor.data_dir)
        self._decode_selected_packet()

    def _selected_packet(self) -> ReassembledPacket | None:
        """Return the currently selected packet, if any."""
        if self.document is None:
            return None
        selected = self.tree.selection()
        if not selected:
            return None
        packet_index = self._packet_index_by_row_id.get(selected[0])
        if packet_index is None:
            return None
        return self.document.packets[packet_index]

    def _on_packet_selected(self, _event: tk.Event) -> None:
        """Handle the event when a packet is selected in the treeview."""
        self._decode_selected_packet()

    def _plugin_manager(self):
        """Return the plugin manager, or a default if none is available."""
        return getattr(self, "_lua_plugin_manager", NO_LUA_PLUGINS)

    def _on_packet_edit_started(self, cell: tuple[str, str]) -> None:
        """Handle the event when packet editing is started."""
        if cell[1] != self.PACKET_HEX_COLUMN_ID:
            return
        self._packet_hex_row_id = cell[0]
        self._packet_hex_original_text = self.tree.get_cell_value(cell)

    def _on_packet_hex_finished(self, event: tk.Event) -> None:
        """Handle the event when packet hex editing is finished."""
        row_id = self._packet_hex_row_id
        self._packet_hex_row_id = None
        if row_id is None or self.document is None:
            return
        text = event.widget.get().strip()
        if text == self._packet_hex_original_text:
            return
        packet_index = self._packet_index_by_row_id.get(row_id)
        if packet_index is None:
            return
        packet = self.document.packets[packet_index]
        try:
            value = bytes.fromhex(text)
            packet.replace_data(self.document.data, value)
        except ValueError as exc:
            messagebox.showerror("Hex Error", str(exc), parent=self)
        self._refresh_packets(packet.sequence)
        self._decode_selected_packet()

    def _decode_selected_packet(self) -> None:
        """Decode the currently selected packet, if any, and update the UI."""
        packet = self._selected_packet()
        self.struct_layout = None
        self.struct_instance = None
        if packet is not None and packet.complete:
            try:
                self.struct_layout = matching_struct_layout(
                    self.payload_struct_defs, packet)
                if self.struct_layout is not None:
                    self.struct_instance = self._decode_with_progress(
                        self.struct_layout,
                        packet.data,
                    )
            except OperationCanceledError:
                return
            except (TypeError, ValueError, NameError, SyntaxError) as exc:
                messagebox.showerror("Decode Error", str(exc), parent=self)
        label = (f"Payload: {self.struct_layout.struct_def_name}"
                 if self.struct_layout is not None else "Payload: Hex only")
        self.definition_label.configure(text=label)
        self._refresh_detail_tree()

    def _on_detail_edit_started(self, cell: tuple[str, str]) -> None:
        """Handle the event when detail editing is started."""
        if cell[1] != self.DETAIL_VALUE_COLUMN_ID:
            return
        self._detail_value_row_id = cell[0]
        self._detail_value_original_text = self.detail_tree.get_cell_value(cell)

    def _on_detail_value_finished(self, event: tk.Event) -> None:
        """Handle the event when detail value editing is finished."""
        row_id = self._detail_value_row_id
        self._detail_value_row_id = None
        packet = self._selected_packet()
        if (row_id is None or packet is None or self.struct_instance is None
                or self.struct_layout is None or self.document is None):
            return
        text = event.widget.get()
        if text == self._detail_value_original_text:
            return
        try:
            updated_instance = replace_instance_value(
                self.struct_instance,
                self._detail_path_by_row_id[row_id],
                text,
                self.struct_layout.type_dict,
            )
            encoded_instance = self._plugin_manager().apply_encode(
                updated_instance)
            encoded = encode(self.struct_layout, encoded_instance, bytearray())
            packet.replace_data(self.document.data, encoded)
            self.struct_instance = self._decode_with_progress(
                self.struct_layout,
                packet.data,
            )
        except OperationCanceledError:
            return
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            messagebox.showerror("Value Error", str(exc), parent=self)
        self._refresh_packets(packet.sequence)
        self._refresh_detail_tree()

    def _refresh_detail_tree(self) -> None:
        """Refresh the detail tree view to reflect
           the current struct instance."""
        self._detail_path_by_row_id = {}
        self.detail_tree.delete(*self.detail_tree.get_children())
        if self.struct_instance is not None:
            self._insert_instance(self.struct_instance, "", InfoSize())

    def _insert_instance(
            self,
            instance: object,
            parent_id: str,
            base_offset: InfoSize,
            field_path: tuple[int, ...] = (),
    ) -> None:
        """Insert an instance and its fields into the detail tree view."""
        packet = self._selected_packet()
        if packet is None:
            return
        for field_index, field_instance in enumerate(instance.field_instances):
            field_def = field_instance.field_def
            offset = base_offset + field_def.offset
            field_bytes = bits_get(packet.data, offset, field_def.size).to_bytes
            row_id = self.detail_tree.insert(
                parent_id,
                tk.END,
                values=(
                    format_infosize(offset),
                    field_def.name,
                    format_type(field_def.type),
                    format_value(field_instance.value),
                    format_infosize(field_def.size),
                    field_bytes.hex(" ").upper(),
                ),
                open=True,
            )
            current_path = field_path + (field_index, )
            self._detail_path_by_row_id[row_id] = current_path
            if hasattr(field_instance.value, "field_instances"):
                self.detail_tree.set_readonly_cell(
                    (row_id, self.DETAIL_VALUE_COLUMN_ID), True)
                self._insert_instance(field_instance.value, row_id, offset,
                                      current_path)

    def _save_capture(self) -> None:
        """Save the current capture to its file, prompting
           for a location if necessary."""
        if self.capture_file is None:
            self._save_capture_as()
            return
        self._write_capture(self.capture_file)

    def _save_capture_as(self) -> None:
        """Prompt the user to save the current capture to a new file."""
        if self.document is None:
            messagebox.showerror("No Capture",
                                 "Open a capture file first.",
                                 parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Save Capture",
            initialdir=self.data_dir,
            defaultextension=f".{self.document.capture_format}",
            filetypes=[("Capture files", "*.pcap *.pcapng"),
                       ("All files", "*.*")],
        )
        if path:
            self._write_capture(Path(path))

    def _write_capture(self, path: Path) -> None:
        """Write the current capture to the specified file path."""
        if self.document is None:
            messagebox.showerror("No Capture",
                                 "Open a capture file first.",
                                 parent=self)
            return
        try:
            self.document.save(path)
        except OSError as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)
            return
        self.capture_file = path
        self._remember_data_dir(path)
        messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)

    def _refresh_packets(self, selected_sequence: int | None = None) -> None:
        """Refresh the packet list tree view, optionally selecting
           a specific packet."""
        self._packet_index_by_row_id = {}
        self.tree.delete(*self.tree.get_children())
        if self.document is None:
            return
        for index, packet in enumerate(self.document.packets):
            row_id = str(index)
            self._packet_index_by_row_id[row_id] = index
            protocol = self.PROTOCOL_NAMES.get(packet.protocol,
                                               str(packet.protocol))
            identification = ("" if packet.identification is None else
                              f"0x{packet.identification:08X}")
            self.tree.insert(
                "",
                tk.END,
                iid=row_id,
                text="Packet",
                values=(
                    packet.sequence + 1,
                    packet.timestamps.get("timestamp", ""),
                    packet.ip_version,
                    packet.source,
                    packet.destination,
                    protocol,
                    identification,
                    len(packet.data),
                    "Complete" if packet.complete else "Incomplete",
                    " ".join(f"{value:02X}" for value in packet.data),
                ),
                open=True,
            )
            if not packet.complete:
                self.tree.set_readonly_cell((row_id, self.PACKET_HEX_COLUMN_ID),
                                            True)
            visible_fragments = (packet.fragments
                                 if len(packet.fragments) > 1 else ())
            for fragment_index, fragment in enumerate(visible_fragments):
                fragment_row_id = f"{index}:fragment:{fragment_index}"
                self._packet_index_by_row_id[fragment_row_id] = index
                fragment_data = self.document.data[
                    fragment.capture_offset:fragment.capture_offset +
                    fragment.length]
                self.tree.insert(
                    row_id,
                    tk.END,
                    iid=fragment_row_id,
                    text="Fragment",
                    values=(
                        fragment.sequence + 1,
                        fragment.timestamps.get("timestamp", ""),
                        "",
                        "",
                        "",
                        "",
                        "",
                        fragment.length,
                        f"Offset {fragment.payload_offset}",
                        " ".join(f"{value:02X}" for value in fragment_data),
                    ),
                )
                self.tree.set_readonly_cell(
                    (fragment_row_id, self.PACKET_HEX_COLUMN_ID), True)
            if selected_sequence == packet.sequence:
                self.tree.selection_set(row_id)
        self.status_label.configure(
            text=(f"{self.capture_file.name}: {len(self.document.packets)} "
                  "IP packet(s)"))


def main() -> None:
    """Entry point for the packet data editor application."""
    root = tk.Tk()
    root.withdraw()
    editor = PacketDataEditorWindow(root)
    editor.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
