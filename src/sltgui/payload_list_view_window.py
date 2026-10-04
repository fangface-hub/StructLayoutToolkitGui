"""Read-only list view of decoded payload fields for matching packets."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from sltcodec import decode
from sltmodel.payload_struct_defs import matching_struct_layout
from sltmodel.struct_instance import format_field_value
from tkinterex import OperationCanceledError, run_with_progress
from treeviewex import TreeviewEx


class PayloadListViewWindow(tk.Toplevel):
    """List the fields of packets matching a PayloadStructDef condition.

    Each packet is one row: the packet columns of the editor's upper pane
    are followed by one column per decoded field (the editor's lower pane
    transposed). Packet data is read through ``virtual_bytearray`` without
    copying.
    """

    PACKET_COLUMNS = (
        ("sequence", "No.", 60),
        ("timestamp", "Timestamp", 200),
        ("version", "IP", 50),
        ("source", "Source", 150),
        ("destination", "Destination", 150),
        ("protocol", "Protocol", 80),
        ("identification", "Identification", 110),
        ("length", "Length", 70),
        ("status", "Status", 90),
    )
    FIELD_PREFIX = "f"

    def __init__(self, parent: tk.Misc, editor) -> None:
        """Initialize the window using the data held by ``editor``."""
        super().__init__(parent)
        self.editor = editor
        self.title("Payload List View")
        self.geometry("1080x620")
        self._build_ui()
        self._refresh_definitions()

    def _build_ui(self) -> None:
        """Build the widgets."""
        tree_style = "PayloadList.Treeview"
        ttk.Style(self).configure(tree_style, font="TkFixedFont")
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Payload condition:").pack(side=tk.LEFT)
        self.definition_combo = ttk.Combobox(toolbar, state="readonly")
        self.definition_combo.pack(side=tk.LEFT,
                                   fill=tk.X,
                                   expand=True,
                                   padx=(4, 0))
        self.definition_combo.bind("<<ComboboxSelected>>",
                                   self._on_definition_selected)

        frame = ttk.Labelframe(self, text="Matching packets")
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        self.tree = TreeviewEx(frame,
                               columns=tuple(c for c, _, _ in self.PACKET_COLUMNS),
                               show="headings",
                               selectmode="browse",
                               style=tree_style)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self._configure_columns(())

        self.status_label = ttk.Label(self,
                                      text="Select a payload condition.",
                                      padding=(8, 0, 8, 8))
        self.status_label.pack(fill=tk.X)

    def _configure_columns(self, field_names: tuple[str, ...]) -> None:
        """Set packet columns followed by one column per field."""
        columns = tuple(c for c, _, _ in self.PACKET_COLUMNS) + tuple(
            f"{self.FIELD_PREFIX}{i}" for i in range(len(field_names)))
        self.tree.configure(columns=columns, displaycolumns=columns)
        for column, heading, width in self.PACKET_COLUMNS:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, minwidth=40, anchor=tk.W)
        for index, name in enumerate(field_names):
            column = f"{self.FIELD_PREFIX}{index}"
            self.tree.heading(column, text=name)
            self.tree.column(column, width=120, minwidth=40, anchor=tk.W)
        for column_id in range(1, len(columns) + 1):
            self.tree.set_readonly_column(f"#{column_id}", True)

    def _refresh_definitions(self) -> None:
        """Fill the condition list from the editor's definitions."""
        definitions = self.editor.payload_struct_defs
        self.definition_combo.configure(values=[
            f"{definition.condition}  [{definition.struct_layout.struct_def_name}]"
            for definition in definitions
        ])
        if definitions:
            self.definition_combo.current(0)
            self._on_definition_selected()

    def _on_definition_selected(self, _event: tk.Event | None = None) -> None:
        """Rebuild the list for the selected definition."""
        index = self.definition_combo.current()
        definitions = self.editor.payload_struct_defs
        self.tree.delete(*self.tree.get_children())
        if self.editor.document is None or not 0 <= index < len(definitions):
            self.status_label.configure(text="No capture or definition.")
            return
        try:
            field_names, rows = collect_payload_rows(self.editor, self,
                                                     definitions[index])
        except OperationCanceledError:
            return
        except (TypeError, ValueError, NameError, SyntaxError,
                AttributeError) as exc:
            messagebox.showerror("Decode Error", str(exc), parent=self)
            return
        self._configure_columns(tuple(field_names))
        for row in rows:
            self.tree.insert("", tk.END, values=row)
        self.status_label.configure(text=f"{len(rows)} matching packet(s)")


def _collect_fields(instance, layout, prefix: str,
                    fields: dict[str, str]) -> None:
    """Flatten instance fields into ``fields`` keyed by dotted name."""
    for field_instance in instance.field_instances:
        name = f"{prefix}{field_instance.field_def.name}"
        if hasattr(field_instance.value, "field_instances"):
            _collect_fields(field_instance.value, layout, f"{name}.", fields)
        else:
            fields[name] = format_field_value(field_instance,
                                              layout.type_dict)


def collect_payload_rows(editor, parent: tk.Misc,
                         definition) -> tuple[list[str], list[tuple]]:
    """Decode packets matching ``definition`` with a progress dialog.

    Returns the field column names and rows (packet columns + fields).
    """
    layout = definition.struct_layout
    packets = editor.document.packets
    total = len(packets)
    plugin_manager = editor._plugin_manager()  # pylint: disable=protected-access
    title = f"Decoding packets ({layout.struct_def_name})..."

    def work(progress_callback) -> tuple[list[str], list[tuple]]:
        field_names: list[str] = []
        known: set[str] = set()
        found = []
        for count, packet in enumerate(packets, 1):
            progress_callback((count - 1) / total)
            if not packet.complete or matching_struct_layout(
                [definition], packet) is None:
                continue
            instance = plugin_manager.apply_decode(decode(layout, packet.data))
            fields: dict[str, str] = {}
            _collect_fields(instance, layout, "", fields)
            for name in fields:
                if name not in known:
                    known.add(name)
                    field_names.append(name)
            found.append((packet, fields))
        progress_callback(1.0)
        rows = []
        for packet, fields in found:
            identification = ("" if packet.identification is None else
                              f"0x{packet.identification:08X}")
            protocol = editor.PROTOCOL_NAMES.get(packet.protocol,
                                                 str(packet.protocol))
            rows.append((
                packet.sequence + 1,
                packet.timestamps.get("timestamp", ""),
                packet.ip_version,
                packet.source,
                packet.destination,
                protocol,
                identification,
                len(packet.data),
                "Complete",
            ) + tuple(fields.get(n, "") for n in field_names))
        return field_names, rows

    return run_with_progress(parent, title, work)