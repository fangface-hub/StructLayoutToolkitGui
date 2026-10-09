"""Editor for reassembled IP packet data in PCAP and PCAPNG files."""
from __future__ import annotations

import csv
import json
import re
import tkinter as tk
from importlib import import_module
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from sltcodec import StructLayout, decode, encode
from sltcore import InfoSize, bits_get
from sltmodel.infosize import format_infosize
from sltmodel.packet_data import CaptureDocument, ReassembledPacket
from sltmodel.payload_struct_defs import matching_struct_layout
from sltmodel.struct_instance import (format_field_value, format_type,
                                      replace_instance_value)
from tkinterex import (OperationCanceledError, run_with_progress,
                       show_modal_window)
from treeviewex import TreeviewEx

if TYPE_CHECKING:
    from .lua_plugins import NO_LUA_PLUGINS, LuaPluginManager
elif __package__:
    lua_plugins_module = import_module(".lua_plugins", __package__)
    LuaPluginManager = lua_plugins_module.LuaPluginManager
    NO_LUA_PLUGINS = lua_plugins_module.NO_LUA_PLUGINS
else:
    lua_plugins_module = import_module("lua_plugins")
    LuaPluginManager = lua_plugins_module.LuaPluginManager
    NO_LUA_PLUGINS = lua_plugins_module.NO_LUA_PLUGINS


def _to_bytes(data: object) -> bytes:
    """Return a contiguous bytes snapshot of bytes-like or virtual data."""
    if hasattr(data, "to_bytes") and not isinstance(data, int):
        return data.to_bytes()
    return bytes(data)


def _hex_text(data: object) -> str:
    """Return upper-case space separated hex using C-level conversion."""
    return _to_bytes(data).hex(" ").upper()


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
    DETAIL_VALUE_COLUMN_ID = "#4"
    DETAIL_HEX_COLUMN_ID = "#6"
    PROTOCOL_NAMES = {1: "ICMP", 6: "TCP", 17: "UDP", 58: "ICMPv6"}

    def _decode_with_progress(
        self,
        struct_layout: StructLayout,
        data: object,
        title: str = "Decoding packet...",
    ) -> object:
        """Decode packet data and apply the configured decode plugin."""
        instance = run_with_progress(
            self,
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
        self._packet_index_by_row_id: dict[str, int] = {}
        self._detail_value_row_id: str | None = None
        self._detail_value_original_text = ""
        self._detail_raw_row_id: str | None = None
        self._detail_raw_original_text = ""
        self._detail_path_by_row_id: dict[str, tuple[int, ...]] = {}
        self._detail_pending: dict[str, tuple] = {}
        self.bytes_per_row = 4
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
        file_menu.add_command(label="Export PayloadList",
                              command=self._export_payload_list)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        definition_menu = tk.Menu(menubar, tearoff=False)
        definition_menu.add_command(
            label="Payload Struct Definitions...",
            command=self._open_payload_struct_def_editor,
        )
        menubar.add_cascade(label="Packet Definition", menu=definition_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="PayloadListView",
                              command=self._open_payload_list_view)
        menubar.add_cascade(label="View", menu=view_menu)
        self.config(menu=menubar)

    def _export_payload_list(self) -> None:
        """Export each payload condition's list as a separate CSV file."""
        if self.document is None or not self.payload_struct_defs:
            messagebox.showerror(
                "Export Error",
                "Open a capture and define payload conditions first.",
                parent=self)
            return
        directory = filedialog.askdirectory(title="Export PayloadList",
                                            initialdir=self.data_dir,
                                            parent=self)
        if not directory:
            return
        module_name = (f"{__package__}.payload_list_view_window"
                       if __package__ else "payload_list_view_window")
        view_module = import_module(module_name)
        headings = [heading for _, heading, _ in
                    view_module.PayloadListViewWindow.PACKET_COLUMNS]
        written = []
        try:
            for index, definition in enumerate(self.payload_struct_defs, 1):
                field_names, rows = view_module.collect_payload_rows(
                    self, self, definition)
                name = re.sub(r'[\\/:*?"<>|\s]+', "_",
                              definition.struct_layout.struct_def_name
                              ).strip("_") or "payload"
                path = Path(directory) / f"{index:02d}_{name}.csv"
                with path.open("w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow([*headings, *field_names])
                    writer.writerows(rows)
                written.append(path)
        except OperationCanceledError:
            return
        except (OSError, TypeError, ValueError, NameError, SyntaxError,
                AttributeError) as exc:
            messagebox.showerror("Export Error", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Exported",
            f"Exported {len(written)} file(s) to:\n{directory}",
            parent=self)

    def _open_payload_list_view(self) -> None:
        """Open the read-only payload list view window."""
        module_name = (f"{__package__}.payload_list_view_window"
                       if __package__ else "payload_list_view_window")
        window_class = import_module(module_name).PayloadListViewWindow
        window_class(self, self)

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
        for column_id in range(1, len(self.COLUMNS) + 1):
            self.tree.set_readonly_column(f"#{column_id}", True)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_packet_selected)

        detail_toolbar = ttk.Frame(detail_frame, padding=(6, 4))
        detail_toolbar.pack(fill=tk.X)
        ttk.Label(detail_toolbar, text="Bytes/row:").pack(side=tk.LEFT)
        self.bytes_per_row_combo = ttk.Combobox(
            detail_toolbar,
            state="readonly",
            width=4,
            values=(1, 2, 4, 8, 16),
        )
        self.bytes_per_row_combo.set(str(self.bytes_per_row))
        self.bytes_per_row_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.bytes_per_row_combo.bind(
            "<<ComboboxSelected>>",
            self._on_bytes_per_row_changed,
        )

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
        self._set_detail_raw_mode(True)
        self.detail_tree.pack(fill=tk.BOTH, expand=True)
        self.detail_tree.on_edit_started = self._on_detail_edit_started
        self.detail_tree.lazy_loader = self._load_detail_children
        self.detail_tree.bind("<<TreeviewOpen>>", self._on_detail_open)
        self.detail_tree.entry.bind("<Return>",
                                    self._on_detail_raw_hex_finished,
                                    add="+")
        self.detail_tree.entry.bind("<FocusOut>",
                                    self._on_detail_raw_hex_finished,
                                    add="+")
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
            document = run_with_progress(
                self,
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
            except (TypeError, ValueError, NameError, SyntaxError,
                    AttributeError) as exc:
                messagebox.showerror("Decode Error", str(exc), parent=self)
        label = (f"Payload: {self.struct_layout.struct_def_name}"
                 if self.struct_layout is not None else "Payload: Hex only")
        self.definition_label.configure(text=label)
        self._refresh_detail_tree()

    def _on_detail_edit_started(self, cell: tuple[str, str]) -> None:
        """Handle the event when detail editing is started."""
        if cell[1] == self.DETAIL_HEX_COLUMN_ID and cell[0].startswith("raw-"):
            self._detail_raw_row_id = cell[0]
            self._detail_raw_original_text = self.detail_tree.get_cell_value(
                cell)
        elif cell[1] == self.DETAIL_VALUE_COLUMN_ID:
            self._detail_value_row_id = cell[0]
            self._detail_value_original_text = self.detail_tree.get_cell_value(
                cell)

    def _on_detail_raw_hex_finished(self, event: tk.Event) -> None:
        """Write an edited raw payload row back to the selected packet."""
        row_id = self._detail_raw_row_id
        self._detail_raw_row_id = None
        packet = self._selected_packet()
        if (row_id is None or packet is None or self.struct_instance is not None
                or self.document is None):
            return
        text = event.widget.get().strip()
        if text == self._detail_raw_original_text:
            return
        offset = int(row_id[4:])
        byte_count = min(self.bytes_per_row, len(packet.data) - offset)
        try:
            values = bytes.fromhex(text)
            if len(values) != byte_count:
                raise ValueError(
                    f"Hex data must contain exactly {byte_count} bytes.")
            updated_data = bytearray(packet.data)
            updated_data[offset:offset + byte_count] = values
            packet.replace_data(self.document.data, bytes(updated_data))
        except ValueError as exc:
            messagebox.showerror("Hex Error", str(exc), parent=self)
            self._refresh_detail_tree()
            return
        self._refresh_packets(packet.sequence)
        self._decode_selected_packet()

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
        self._detail_raw_row_id = None
        self._detail_value_row_id = None
        self._detail_path_by_row_id = {}
        self._detail_pending = {}
        self.detail_tree.delete(*self.detail_tree.get_children())
        if self.struct_instance is not None:
            self._set_detail_raw_mode(False)
            self._insert_instance(self.struct_instance, "", InfoSize())
        else:
            self._set_detail_raw_mode(True)
            packet = self._selected_packet()
            if packet is not None and packet.complete:
                self._insert_raw_payload(packet.data)

    def _on_bytes_per_row_changed(self, _event: tk.Event) -> None:
        """Rebuild raw payload rows using the selected byte count."""
        self.bytes_per_row = int(self.bytes_per_row_combo.get())
        if self.struct_instance is None:
            self._refresh_detail_tree()

    def _set_detail_raw_mode(self, raw_mode: bool) -> None:
        """Switch editable detail columns between raw and struct modes."""
        for column_id in ("#1", "#2", "#3", "#5"):
            self.detail_tree.set_readonly_column(column_id, True)
        self.detail_tree.set_readonly_column(self.DETAIL_VALUE_COLUMN_ID,
                                             raw_mode)
        self.detail_tree.set_readonly_column(self.DETAIL_HEX_COLUMN_ID,
                                             not raw_mode)
        self.bytes_per_row_combo.configure(
            state="readonly" if raw_mode else "disabled")

    def _insert_raw_payload(self, data: bytes | bytearray) -> None:
        """Insert raw payload bytes into fixed-width editable rows."""
        for offset in range(0, len(data), self.bytes_per_row):
            values = data[offset:offset + self.bytes_per_row]
            self.detail_tree.insert(
                "",
                tk.END,
                iid=f"raw-{offset}",
                values=(
                    f"{offset},0",
                    "",
                    "",
                    "",
                    f"{len(values)},0",
                    _hex_text(values),
                ),
            )

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
        self._insert_instance_rows(instance, parent_id, base_offset,
                                   field_path, _to_bytes(packet.data))

    def _insert_instance_rows(
            self,
            instance: object,
            parent_id: str,
            base_offset: InfoSize,
            field_path: tuple[int, ...],
            data: bytes,
    ) -> None:
        """Insert fields recursively using one shared payload snapshot."""
        insert = self.detail_tree.insert
        type_dict = self.struct_layout.type_dict
        for field_index, field_instance in enumerate(instance.field_instances):
            field_def = field_instance.field_def
            offset = base_offset + field_def.offset
            field_bytes = bits_get(data, offset, field_def.size).to_bytes
            row_id = insert(
                parent_id,
                tk.END,
                values=(
                    format_infosize(offset),
                    field_def.name,
                    format_type(field_def.type),
                    format_field_value(field_instance, type_dict),
                    format_infosize(field_def.size),
                    field_bytes.hex(" ").upper(),
                ),
                open=False,
            )
            current_path = field_path + (field_index, )
            self._detail_path_by_row_id[row_id] = current_path
            if hasattr(field_instance.value, "field_instances"):
                self.detail_tree.set_readonly_cell(
                    (row_id, self.DETAIL_VALUE_COLUMN_ID), True)
                placeholder = insert(row_id, tk.END)
                self._detail_pending[row_id] = (field_instance.value, offset,
                                                current_path, placeholder)

    def _on_detail_open(self, _event: tk.Event) -> None:
        """Create children of the node being opened."""
        row_id = self.detail_tree.focus()
        if row_id:
            self._load_detail_children(row_id)

    def _load_detail_children(self, row_id: str) -> None:
        """Replace a placeholder with the real child rows on first open."""
        pending = self._detail_pending.pop(row_id, None)
        if pending is None:
            return
        instance, offset, path, placeholder = pending
        packet = self._selected_packet()
        if packet is None:
            return
        self.detail_tree.delete(placeholder)
        self._insert_instance_rows(instance, row_id, offset, path,
                                   _to_bytes(packet.data))

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

    def _update_selected_in_place(self, sequence: int) -> bool:
        """Update the edited packet rows without rebuilding the list.

        Returns False when the tree does not mirror the document, so the
        caller must rebuild it.
        """
        document = self.document
        row_map = getattr(self, "_packet_index_by_row_id", None)
        if document is None or not row_map:
            return False
        selected = self.tree.selection()
        index = row_map.get(selected[0]) if selected else None
        if (index is None or index >= len(document.packets)
                or document.packets[index].sequence != sequence
                or len(self.tree.get_children()) != len(document.packets)):
            return False
        packet = document.packets[index]
        row_id = str(index)
        values = list(self.tree.item(row_id, "values"))
        values[-1] = _hex_text(packet.data)
        self.tree.item(row_id, values=values)
        for fragment_index in range(len(self.tree.get_children(row_id))):
            fragment = packet.fragments[fragment_index]
            fragment_row_id = f"{index}:fragment:{fragment_index}"
            fragment_values = list(self.tree.item(fragment_row_id, "values"))
            fragment_values[-1] = _hex_text(self.document.data[
                fragment.capture_offset:fragment.capture_offset +
                fragment.length])
            self.tree.item(fragment_row_id, values=fragment_values)
        return True

    def _refresh_packets(self, selected_sequence: int | None = None) -> None:
        """Refresh the packet list tree view, optionally selecting
           a specific packet."""
        if selected_sequence is not None and self._update_selected_in_place(
                selected_sequence):
            return
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
            packet_hex = _hex_text(packet.data)
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
                    packet_hex,
                ),
                open=True,
            )
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
                        _hex_text(fragment_data),
                    ),
                )
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
