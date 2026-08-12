"""StructDef Dict Editor Window."""
from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from sltcodec import PRIMITIVE_TYPES, FieldDef, StructDef, TypeDict
from sltcore import InfoSize
from tkinterex import ComboboxEx, EntryEx, TextEx, show_modal_window
from treeviewex import TreeviewEx

FIELD_COLUMNS = (
    "name",
    "offset",
    "size",
    "type",
    "scale",
    "repeat",
    "description",
    "range_expression",
    "enum_def_name",
    "byte_swap",
)

PRIMITIVE_TYPES = tuple(sorted(PRIMITIVE_TYPES))
TYPE_COLUMN_ID = "#4"
OFFSET_COLUMN_ID = "#2"
SIZE_COLUMN_ID = "#3"
ENUM_DEF_COLUMN_ID = "#9"


@dataclass(frozen=True)
class _OffsetShift:
    """Data structure to hold offset shift information."""
    sign: str
    amount: InfoSize


class _HeadingToolTip:
    """Show a short input-format hint for field-tree headings."""

    def __init__(self, widget: ttk.Treeview, messages: dict[str, str]) -> None:
        """Initialize the tooltip for the given widget and messages."""
        self.widget = widget
        self.messages = messages
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _on_motion(self, event: tk.Event) -> None:
        """Handle mouse motion events over the widget to show tooltips."""
        if self.widget.identify_region(event.x, event.y) != "heading":
            self._hide()
            return
        column_id = self.widget.identify_column(event.x)
        message = self.messages.get(column_id)
        if message is None:
            self._hide()
            return
        self._hide()
        self.after_id = self.widget.after(
            500,
            lambda: self._show(message, event.x_root + 12, event.y_root + 12),
        )

    def _show(self, message: str, x: int, y: int) -> None:
        """Show the tooltip window with the given message
           at the specified position."""
        self.after_id = None
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        ttk.Label(
            self.window,
            text=message,
            justify=tk.LEFT,
            relief=tk.SOLID,
            borderwidth=1,
            padding=6,
        ).pack()

    def _hide(self, _event: tk.Event | None = None) -> None:
        """Hide the tooltip window if it is currently shown."""
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class StructDefDictEditor(tk.Toplevel):
    """GUI editor for struct definitions in sltcodec type_dict JSON files."""

    enum_def_dict: dict[str, dict] = {}

    def __init__(
        self,
        parent: tk.Misc,
        type_dict: TypeDict | None = None,
    ) -> None:
        """Initialize the StructDefDictEditor."""
        super().__init__(parent)
        # Stay hidden while widgets are built to avoid a partial-render flicker.
        self.withdraw()
        self.title("StructDef Dict Editor")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = min(1280, max(640, screen_width - 80))
        window_height = min(760, max(480, screen_height - 100))
        # Position is left to show_modal_window(); setting it here too would
        # make the window visibly jump once show_modal_window repositions it.
        self.geometry(f"{window_width}x{window_height}")
        # Wide field_tree columns would otherwise inflate winfo_reqwidth
        # beyond the requested size, breaking modal placement.
        self.config(width=window_width, height=window_height)
        self.pack_propagate(False)

        self.type_dict = type_dict if type_dict is not None else TypeDict()
        self.struct_data: dict[str, dict] = {}
        self.enum_def_dict = {}
        type(self).enum_def_dict = self.enum_def_dict
        self.current_struct_key: str | None = None
        self._initial_field_size = InfoSize(4, 0)
        self._initial_field_type = "unsigned int"

        self._build_ui()
        self._load_type_dict_data()

    def _build_ui(self) -> None:
        """Build the struct definition editor interface."""
        self._build_button_bar()

        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, padding=8, width=280)
        right_frame = ttk.Frame(main_pane, padding=8)
        main_pane.add(left_frame, weight=0)
        main_pane.add(right_frame, weight=1)

        ttk.Label(left_frame, text="Structs").pack(anchor="w")
        left_btns = ttk.Frame(left_frame)
        left_btns.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(
            left_btns,
            text="Add Struct",
            command=self._add_struct,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            left_btns,
            text="Remove Struct",
            command=self._remove_struct,
        ).pack(side=tk.LEFT)

        self.struct_tree = TreeviewEx(
            left_frame,
            columns=("name", ),
            show="headings",
            selectmode="browse",
            height=25,
        )
        self.struct_tree.heading("name", text="Name")
        self.struct_tree.column("name", width=220, anchor=tk.W)
        self.struct_tree.set_readonly_column("#1")
        self.struct_tree.pack(fill=tk.BOTH, expand=True)
        self.struct_tree.bind("<<TreeviewSelect>>", self._on_struct_selected)

        meta_frame = ttk.LabelFrame(right_frame, text="Struct Meta", padding=8)
        meta_frame.pack(fill=tk.X)
        ttk.Label(meta_frame, text="Name").grid(row=0, column=0, sticky="w")
        self.name_entry = EntryEx(meta_frame)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(meta_frame, text="Description").grid(
            row=1,
            column=0,
            sticky="nw",
            pady=(8, 0),
        )
        self.description_text = TextEx(meta_frame, height=3)
        self.description_text.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )
        ttk.Button(
            meta_frame,
            text="Update Meta",
            command=self._update_struct_meta,
        ).grid(row=2, column=1, sticky="e", padx=(8, 0), pady=(8, 0))
        meta_frame.columnconfigure(1, weight=1)

        field_frame = ttk.LabelFrame(right_frame, text="Fields", padding=8)
        field_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        field_btns = ttk.Frame(field_frame)
        field_btns.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            field_btns,
            text="Add Field",
            command=self._add_field,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            field_btns,
            text="Insert Field",
            command=self._insert_field,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            field_btns,
            text="Remove Field",
            command=self._remove_field,
        ).pack(side=tk.LEFT)
        ttk.Button(
            field_btns,
            text="Shift Offset",
            command=self._shift_selected_offsets,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            field_btns,
            text="Update Multi-line Size",
            command=self._update_selected_sizes,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            field_btns,
            text="Initial Size",
            command=self._set_initial_field_size,
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.initial_size_label = ttk.Label(
            field_btns,
            text=self._format_initial_size(),
        )
        self.initial_size_label.pack(side=tk.LEFT, padx=(4, 12))
        self.initial_type_combo = ComboboxEx(
            field_btns,
            state="readonly",
            values=list(PRIMITIVE_TYPES),
            width=12,
        )
        self.initial_type_combo.value = self._initial_field_type
        self.initial_type_combo.pack(side=tk.LEFT)
        self.initial_type_combo.bind(
            "<<ComboboxSelected>>",
            self._on_initial_type_changed,
        )

        self.field_tree = TreeviewEx(
            field_frame,
            columns=FIELD_COLUMNS,
            show="headings",
            selectmode="extended",
            height=16,
        )
        self.field_tree.pack(fill=tk.BOTH, expand=True)

        for col in FIELD_COLUMNS:
            self.field_tree.heading(col, text=col)

        self.field_tree.column("name", width=170, anchor=tk.W)
        self.field_tree.column("offset", width=180, anchor=tk.W)
        self.field_tree.column("size", width=180, anchor=tk.W)
        self.field_tree.column("type", width=120, anchor=tk.W)
        self.field_tree.column("scale", width=80, anchor=tk.W)
        self.field_tree.column("repeat", width=80, anchor=tk.W)
        self.field_tree.column("description", width=230, anchor=tk.W)
        self.field_tree.column("range_expression", width=190, anchor=tk.W)
        self.field_tree.column("enum_def_name", width=280, anchor=tk.W)
        self.field_tree.column("byte_swap", width=100, anchor=tk.W)

        # TreeviewEx uses numeric column IDs like "#4" for each column.
        self.field_tree.set_combobox_column(
            TYPE_COLUMN_ID,
            values=list(PRIMITIVE_TYPES),
        )
        self.field_tree.set_combobox_column(
            ENUM_DEF_COLUMN_ID,
            values=[],
        )
        self.field_tree.set_combobox_column(
            "#10",
            values=["True", "False"],
        )
        _HeadingToolTip(
            self.field_tree,
            {
                OFFSET_COLUMN_ID:
                ("InfoSize: byte,bit (e.g. 1,3) or expression "
                 "(e.g. field_a.size * 2)"),
                SIZE_COLUMN_ID: ("InfoSize: byte,bit (e.g. 0,4) or expression "
                                 "(e.g. field_a.size + 1)"),
            },
        )

    def _build_button_bar(self) -> None:
        """Build the Cancel/Update button bar."""
        button_bar = ttk.Frame(self, padding=8)
        button_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(
            button_bar,
            text="Update",
            command=self._on_update,
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(
            button_bar,
            text="Cancel",
            command=self._on_cancel,
        ).pack(side=tk.RIGHT)

    def _on_cancel(self) -> None:
        """Close the editor without applying any changes."""
        self.destroy()

    def _on_update(self) -> None:
        """Apply the edited struct definitions to the shared TypeDict."""
        if not self._flush_current_editor():
            return

        struct_dict = self.type_dict.struct_dict
        struct_dict.clear()
        struct_dict.update(self._to_struct_def_dict())
        self.destroy()

    def _refresh_enum_combobox_values(self) -> None:
        """Refresh the enum_def combobox column of the field tree."""
        values = sorted(self.enum_def_dict.keys())
        self.field_tree.set_combobox_column(ENUM_DEF_COLUMN_ID, values=values)

    def _load_type_dict_data(self) -> None:
        """Populate the editor from the current shared TypeDict."""
        self.struct_data = {
            key: self._struct_def_to_data(struct_def)
            for key, struct_def in self.type_dict.struct_dict.items()
        }
        self.enum_def_dict = {
            key: {
                **enum_def.to_dict(), "__type__": "EnumDef"
            }
            for key, enum_def in self.type_dict.enum_dict.items()
        }
        type(self).enum_def_dict = self.enum_def_dict
        self._refresh_enum_combobox_values()
        self.current_struct_key = None
        self._refresh_struct_tree()

        struct_keys = list(self.struct_data.keys())
        if struct_keys:
            self._select_struct(struct_keys[0])
        else:
            self._clear_editor()

    def _to_struct_def_dict(self) -> dict[str, StructDef]:
        """Convert the current struct_data to StructDef objects.

        Returns:
            dict[str, StructDef]: Mapping of struct keys to StructDef objects.
        """
        result: dict[str, StructDef] = {}
        for key, value in self.struct_data.items():
            result[key] = StructDef.from_dict(value)
        return result

    @classmethod
    def _struct_def_to_data(cls, struct_def: StructDef) -> dict:
        """Convert a StructDef to editor data with typed static sizes."""
        struct_data = struct_def.to_dict()
        for field_data in struct_data.get("fields", []):
            for field_name in ("offset", "size"):
                field_data[field_name] = cls._parse_infosize_input(
                    field_data.get(field_name, "0,0"))
        return struct_data

    @classmethod
    def _struct_data_to_json_data(
        cls,
        struct_data: dict[str, dict],
    ) -> dict[str, dict]:
        """Prepare struct data for JSON output with typed InfoSize values."""
        result: dict[str, dict] = {}
        for key, struct_dict in struct_data.items():
            json_struct = struct_dict.copy()
            json_fields = []
            for field_dict in struct_dict.get("fields", []):
                json_field = field_dict.copy()
                for field_name in ("offset", "size"):
                    value = json_field.get(field_name, "0,0")
                    input_text = cls._infosize_value_to_string(value)
                    parsed = cls._parse_infosize_input(input_text)
                    if isinstance(parsed, InfoSize):
                        parsed = json.loads(parsed.serialize())
                    json_field[field_name] = parsed
                json_fields.append(json_field)
            json_struct["fields"] = json_fields
            result[key] = json_struct
        return result

    def _refresh_struct_tree(self) -> None:
        """Refresh the struct tree view to reflect the current struct_data."""
        self.struct_tree.delete(*self.struct_tree.get_children())
        for key in self.struct_data:
            self.struct_tree.insert("", tk.END, iid=key, values=(key, ))

    def _clear_editor(self) -> None:
        """Clear the editor fields and reset the field tree."""
        self.name_entry.value = ""
        self.description_text.value = ""
        self.field_tree.delete(*self.field_tree.get_children())
        self._refresh_type_combobox_values()
        self._refresh_enum_combobox_values()

    def _on_struct_selected(self, _event: tk.Event) -> None:
        """Handle the event when a struct is selected in the struct tree."""
        selected = self.struct_tree.selection()
        if not selected:
            return
        new_key = selected[0]

        if self.current_struct_key == new_key:
            return

        if not self._flush_current_editor():
            return
        self._load_struct_to_editor(new_key)

    def _select_struct(self, key: str) -> None:
        """Select a struct in the struct tree and load it into the editor."""
        if key not in self.struct_data:
            return
        self.struct_tree.selection_set(key)
        self.struct_tree.focus(key)
        self.struct_tree.see(key)
        self._load_struct_to_editor(key)

    def _load_struct_to_editor(self, key: str) -> None:
        """Load the struct with the given key into the editor."""
        data = self.struct_data.get(key)
        if data is None:
            self._clear_editor()
            self.current_struct_key = None
            return

        self.current_struct_key = key
        self.name_entry.value = str(data.get("name", key))
        self.description_text.value = str(data.get("description", ""))

        self.field_tree.delete(*self.field_tree.get_children())
        for idx, field_data in enumerate(data.get("fields", []), start=1):
            row_values = self._field_data_to_row_values(field_data)
            self.field_tree.insert(
                "",
                tk.END,
                iid=f"field-{idx}",
                values=row_values,
            )

        self._refresh_type_combobox_values()

    def _flush_current_editor(self) -> bool:
        """Flush the current editor's contents to the struct_data.
        Returns:
            bool: True if the flush was successful, False otherwise.
        """
        if self.current_struct_key is None:
            return True

        old_key = self.current_struct_key
        if old_key not in self.struct_data:
            self.current_struct_key = None
            return True

        new_name = self.name_entry.value.strip()
        if not new_name:
            messagebox.showerror(
                "Validation Error",
                "Struct name cannot be empty.",
            )
            return False

        if new_name != old_key and new_name in self.struct_data:
            messagebox.showerror(
                "Validation Error",
                f"Struct name '{new_name}' already exists.",
            )
            return False

        fields = []
        for row_id in self.field_tree.get_children():
            values = self.field_tree.item(row_id, "values")
            row_map = dict(zip(FIELD_COLUMNS, values))
            try:
                field_dict = self._row_map_to_field_dict(row_map)
            except ValueError as exc:
                messagebox.showerror("Validation Error", str(exc))
                return False
            fields.append(field_dict)

        struct_dict = {
            "name": new_name,
            "description": self.description_text.value,
            "fields": fields,
        }

        if new_name != old_key:
            del self.struct_data[old_key]
            self.struct_data[new_name] = struct_dict
            self.current_struct_key = new_name
            self._refresh_struct_tree()
            self._select_struct(new_name)
        else:
            self.struct_data[old_key] = struct_dict
            self.struct_tree.item(old_key, values=(new_name, ))

        return True

    def _update_struct_meta(self) -> bool:
        """Apply the Struct Meta Data fields immediately."""
        if self.current_struct_key is None:
            return False

        old_key = self.current_struct_key
        if old_key not in self.struct_data:
            return False

        new_name = self.name_entry.value.strip()
        if not new_name:
            messagebox.showerror(
                "Validation Error",
                "Struct name cannot be empty.",
            )
            return False

        if new_name != old_key and new_name in self.struct_data:
            messagebox.showerror(
                "Validation Error",
                f"Struct name '{new_name}' already exists.",
            )
            return False

        struct_dict = self.struct_data.pop(old_key)
        struct_dict["name"] = new_name
        struct_dict["description"] = self.description_text.value
        self.struct_data[new_name] = struct_dict
        self.current_struct_key = new_name
        self._refresh_struct_tree()
        self._select_struct_tree_item(new_name)
        self._refresh_type_combobox_values()
        return True

    def _select_struct_tree_item(self, key: str) -> None:
        """Select a struct tree item without reloading the editor."""
        self.struct_tree.selection_set(key)
        self.struct_tree.focus(key)
        self.struct_tree.see(key)

    def _add_struct(self) -> None:
        """Add a new struct to the struct_data and refresh the editor."""
        if not self._flush_current_editor():
            return

        base = "Struct"
        index = 1
        while f"{base}{index}" in self.struct_data:
            index += 1
        key = f"{base}{index}"

        self.struct_data[key] = {
            "name": key,
            "description": "",
            "fields": [],
        }
        self._refresh_struct_tree()
        self._select_struct(key)

    def _remove_struct(self) -> None:
        """Remove the currently selected struct from the struct_data."""
        selected = self.struct_tree.selection()
        if not selected:
            return

        key = selected[0]
        if key not in self.struct_data:
            return

        del self.struct_data[key]
        self.current_struct_key = None
        self._refresh_struct_tree()

        keys = list(self.struct_data.keys())
        if keys:
            self._select_struct(keys[0])
        else:
            self._clear_editor()

    def _add_field(self) -> None:
        """Add a new field to the currently selected struct in the editor."""
        if self.current_struct_key is None:
            messagebox.showerror("No Struct", "Please select a struct first.")
            return

        existing = self.field_tree.get_children()
        offset = InfoSize()
        if existing:
            last_values = self.field_tree.item(existing[-1], "values")
            try:
                last_offset = self._row_offset_to_infosize(last_values[1])
                last_size = self._row_offset_to_infosize(last_values[2])
                offset = last_offset + last_size
            except (IndexError, TypeError, ValueError) as exc:
                messagebox.showerror("Add Field Error", str(exc))
                return

        field_id, row_values = self._new_field_row(offset)
        self.field_tree.insert(
            "",
            tk.END,
            iid=field_id,
            values=row_values,
        )

    def _insert_field(self) -> None:
        """Insert a new field before the topmost selected field."""
        if self.current_struct_key is None:
            messagebox.showerror("No Struct", "Please select a struct first.")
            return

        existing = self.field_tree.get_children()
        selected = set(self.field_tree.selection())
        selected_index = next(
            (index
             for index, row_id in enumerate(existing) if row_id in selected),
            None,
        )
        if selected_index is None:
            messagebox.showerror(
                "No Field Selected",
                "Select a field to insert before.",
            )
            return

        offset = InfoSize()
        if selected_index > 0:
            previous_values = self.field_tree.item(
                existing[selected_index - 1],
                "values",
            )
            try:
                previous_offset = self._row_offset_to_infosize(
                    previous_values[1])
                previous_size = self._row_offset_to_infosize(previous_values[2])
                offset = previous_offset + previous_size
            except (IndexError, TypeError, ValueError) as exc:
                messagebox.showerror("Insert Field Error", str(exc))
                return

        field_id, row_values = self._new_field_row(offset)
        self.field_tree.insert(
            "",
            selected_index,
            iid=field_id,
            values=row_values,
        )

    def _new_field_row(self, offset: InfoSize) -> tuple[str, tuple[str, ...]]:
        """Create a unique default field row for the given offset."""
        existing_ids = set(self.field_tree.get_children())
        index = 1
        while f"field-{index}" in existing_ids:
            index += 1
        field_id = f"field-{index}"
        initial_size = getattr(self, "_initial_field_size", InfoSize(4, 0))
        initial_type = getattr(
            self,
            "_initial_field_type",
            "unsigned int",
        )
        row_values = (
            f"field_{index}",
            f"{offset.byte},{offset.bit}",
            f"{initial_size.byte},{initial_size.bit}",
            initial_type,
            "1.0",
            "",
            "",
            "",
            "",
            "false",
        )
        return field_id, row_values

    def _format_initial_size(self) -> str:
        """Return the current initial field size for display."""
        initial_size = getattr(self, "_initial_field_size", InfoSize(4, 0))
        return f"{initial_size.byte},{initial_size.bit}"

    def _set_initial_field_size(self) -> None:
        """Set the default size used by newly added fields."""
        size_input = self._ask_infosize_dialog(
            "Initial Size",
            include_sign=False,
            initial_amount=self._initial_field_size,
        )
        if size_input is None:
            return
        self._initial_field_size = size_input.amount
        self.initial_size_label.configure(text=self._format_initial_size())

    def _on_initial_type_changed(self, _event: tk.Event) -> None:
        """Store the type selected for newly added fields."""
        self._initial_field_type = self.initial_type_combo.value

    def _remove_field(self) -> None:
        """Remove the selected field(s) from the currently selected struct
           in the editor."""
        selected = self.field_tree.selection()
        if not selected:
            return
        for row_id in selected:
            self.field_tree.delete(row_id)

    def _shift_selected_offsets(self) -> None:
        """Shift the offsets of the selected fields by a signed amount."""
        selected = self.field_tree.selection()
        if not selected:
            messagebox.showerror(
                "No Fields Selected",
                "Select at least one field first.",
            )
            return

        shift_input = self._ask_offset_shift()
        if shift_input is None:
            return
        sign = shift_input.sign
        shift = shift_input.amount

        new_offsets: dict[str, str] = {}
        try:
            for row_id in selected:
                values = self.field_tree.item(row_id, "values")
                offset = self._row_offset_to_infosize(values[1])
                shifted = (offset + shift if sign == "+" else offset - shift)
                new_offsets[row_id] = f"{shifted.byte},{shifted.bit}"
        except (IndexError, TypeError, ValueError) as exc:
            messagebox.showerror("Shift Offset Error", str(exc))
            return

        for row_id, offset_text in new_offsets.items():
            values = list(self.field_tree.item(row_id, "values"))
            values[1] = offset_text
            self.field_tree.item(row_id, values=values)

    def _update_selected_sizes(self) -> None:
        """Set the size of all selected fields to one InfoSize value."""
        selected = self.field_tree.selection()
        if not selected:
            messagebox.showerror(
                "No Fields Selected",
                "Select at least one field first.",
            )
            return

        size_input = self._ask_infosize_dialog(
            "Update Multi-line Size",
            include_sign=False,
        )
        if size_input is None:
            return

        size_text = f"{size_input.amount.byte},{size_input.amount.bit}"
        for row_id in selected:
            values = list(self.field_tree.item(row_id, "values"))
            values[2] = size_text
            self.field_tree.item(row_id, values=values)

    def _ask_offset_shift(self) -> _OffsetShift | None:
        initial_amount = InfoSize()
        existing = self.field_tree.get_children()
        selected = set(self.field_tree.selection())
        selected_index = next(
            (index
             for index, row_id in enumerate(existing) if row_id in selected),
            None,
        )
        if selected_index is not None and selected_index > 0:
            previous_values = self.field_tree.item(
                existing[selected_index - 1],
                "values",
            )
            try:
                previous_offset = self._row_offset_to_infosize(
                    previous_values[1])
                previous_size = self._row_offset_to_infosize(previous_values[2])
                initial_amount = previous_offset + previous_size
            except (IndexError, TypeError, ValueError) as exc:
                messagebox.showerror("Shift Offset Error", str(exc))
                return None

        return self._ask_infosize_dialog(
            "Shift Offset",
            include_sign=True,
            initial_amount=initial_amount,
        )

    def _ask_infosize_dialog(
        self,
        title: str,
        *,
        include_sign: bool,
        initial_amount: InfoSize | None = None,
    ) -> _OffsetShift | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.resizable(False, False)
        if initial_amount is None:
            initial_amount = InfoSize()

        sign_var = tk.StringVar(value="+")
        input_row = 0
        if include_sign:
            ttk.Label(dialog, text="Sign").grid(
                row=input_row,
                column=0,
                padx=(12, 6),
                pady=(12, 6),
                sticky="w",
            )
            ttk.Combobox(
                dialog,
                textvariable=sign_var,
                values=("+", "-"),
                state="readonly",
                width=4,
            ).grid(row=input_row, column=1, padx=(0, 12), pady=(12, 6))
            input_row += 1

        ttk.Label(dialog, text="Byte").grid(
            row=input_row,
            column=0,
            padx=(12, 6),
            pady=6,
            sticky="w",
        )
        byte_entry = EntryEx(dialog, width=12)
        byte_entry.value = str(initial_amount.byte)
        byte_entry.grid(row=input_row, column=1, padx=(0, 12), pady=6)
        input_row += 1

        ttk.Label(dialog, text="Bit").grid(
            row=input_row,
            column=0,
            padx=(12, 6),
            pady=6,
            sticky="w",
        )
        bit_entry = EntryEx(dialog, width=12)
        bit_entry.value = str(initial_amount.bit)
        bit_entry.grid(row=input_row, column=1, padx=(0, 12), pady=6)
        input_row += 1

        result: list[_OffsetShift | None] = [None]

        def apply_shift() -> None:
            try:
                byte = int(byte_entry.value.strip())
                bit = int(bit_entry.value.strip())
                if byte < 0 or bit < 0:
                    raise ValueError("Byte and bit must be non-negative.")
                sign = sign_var.get() if include_sign else "+"
                result[0] = _OffsetShift(sign, InfoSize(byte, bit))
            except ValueError as exc:
                messagebox.showerror("Invalid Shift", str(exc), parent=dialog)
                return
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply_shift).grid(
            row=input_row,
            column=0,
            padx=(12, 6),
            pady=(6, 12),
        )
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(
            row=input_row,
            column=1,
            padx=(0, 12),
            pady=(6, 12),
        )
        byte_entry.focus_set()
        show_modal_window(self, dialog)
        return result[0]

    @staticmethod
    def _row_offset_to_infosize(value: object) -> InfoSize:
        parsed = StructDefDictEditor._parse_infosize_input(value)
        if isinstance(parsed, InfoSize):
            return parsed
        if not (type(parsed) is dict and parsed.get("__type__") == "InfoSize"):
            raise ValueError(f"Offset expression cannot be shifted: {value}")
        return InfoSize(int(parsed["byte"]), int(parsed["bit"]))

    def _refresh_type_combobox_values(self) -> None:
        """Refresh the values in the type combobox column of the field tree."""
        values = list(PRIMITIVE_TYPES)
        values.extend(sorted(self.struct_data.keys()))
        self.field_tree.set_combobox_column(TYPE_COLUMN_ID, values=values)

    @staticmethod
    def _field_cell_to_string(value: object) -> str:
        """Convert a field cell value to a string for display
           in the treeview."""
        handlers = {
            type(None): lambda _: "",
            bool: lambda item: "true" if item else "false",
            dict: lambda item: json.dumps(item, ensure_ascii=False),
            list: lambda item: json.dumps(item, ensure_ascii=False),
        }
        return handlers.get(type(value), str)(value)

    @staticmethod
    def _parse_json_or_raw(text: str) -> object:
        """Parse a JSON-like cell value, otherwise keep the raw string."""
        text = text.strip()
        if not text:
            return ""
        if not (text.startswith("{") or text.startswith("[")):
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def _infosize_value_to_string(value: object) -> str:
        """Convert an InfoSize value to one editable cell string.
        Parameters:
            value (object): The value to convert, which can be an InfoSize,
              a dict representing an InfoSize, a string, or an int.

        Returns:
            str: The InfoSize ``byte,bit`` form or an expression.
        """

        def from_dict(item: dict) -> str:
            info_size = InfoSize(
                int(item.get("byte", 0)),
                int(item.get("bit", 0)),
            )
            return f"{info_size.byte},{info_size.bit}"

        def from_string(item: str) -> str:
            stripped = item.strip()
            if not stripped:
                return "0,0"
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                try:
                    info_size = InfoSize(int(stripped), 0)
                except ValueError:
                    return stripped
                return f"{info_size.byte},{info_size.bit}"
            if type(parsed) is dict and parsed.get("__type__") == "InfoSize":
                return from_dict(parsed)
            return stripped

        if isinstance(value, InfoSize):
            return f"{value.byte},{value.bit}"

        handlers = {
            dict:
            lambda item: from_dict(item)
            if item.get("__type__") == "InfoSize" else "0,0",
            str:
            from_string,
            int:
            lambda item: from_dict({
                "byte": item,
                "bit": 0
            }),
        }
        return handlers.get(type(value), lambda _: "0,0")(value)

    def _field_data_to_row_values(
        self,
        field_data: dict[str, object],
    ) -> tuple[str, ...]:
        """Convert a field data dictionary to a tuple of row values
           for the treeview.
        Parameters:
            field_data (dict[str, object]): The field data dictionary
            to convert.

        Returns:
            tuple[str, ...]: The row values for the treeview.
        """
        return (
            self._field_cell_to_string(field_data.get("name")),
            self._infosize_value_to_string(field_data.get("offset")),
            self._infosize_value_to_string(field_data.get("size")),
            self._field_cell_to_string(field_data.get("type")),
            self._field_cell_to_string(field_data.get("scale")),
            self._field_cell_to_string(field_data.get("repeat")),
            self._field_cell_to_string(field_data.get("description")),
            self._field_cell_to_string(field_data.get("range_expression")),
            self._field_cell_to_string(field_data.get("enum_def_name") or ""),
            self._field_cell_to_string(field_data.get("byte_swap")),
        )

    def _row_map_to_field_dict(self, row_map: dict[str, object]) -> dict:
        """Convert a row map from the treeview to a field dictionary.

        Parameters:
            row_map (dict[str, object]): The row map from the treeview.

        Returns:
            dict: The corresponding field dictionary.
        """
        name = str(row_map.get("name", "")).strip()
        if not name:
            raise ValueError("Field name cannot be empty.")

        try:
            offset = self._parse_infosize_input(row_map.get("offset", "0,0"))
            size = self._parse_infosize_input(row_map.get("size", "0,0"))
        except ValueError as exc:
            raise ValueError(
                f"Invalid InfoSize for field '{name}': {exc}") from exc

        scale_raw = str(row_map.get("scale", "1.0")).strip() or "1.0"
        try:
            scale = float(scale_raw)
        except ValueError as exc:
            raise ValueError(
                f"Invalid scale for field '{name}': {scale_raw}") from exc

        repeat_raw = str(row_map.get("repeat", "")).strip()
        if not repeat_raw:
            repeat = None
        else:
            try:
                repeat = int(repeat_raw)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid repeat for field '{name}': {repeat_raw}") from exc

        description = str(row_map.get("description", "")).strip() or None
        range_expression = (str(row_map.get("range_expression", "")).strip()
                            or None)
        enum_def = self._parse_enum_def_input(
            row_map.get("enum_def_name", ""),
            self.enum_def_dict,
        )
        byte_swap = row_map.get("byte_swap", False)
        byte_swap_handlers = {
            str: lambda item: item.strip().lower() == "true",
            bool: lambda item: item,
        }
        byte_swap = byte_swap_handlers.get(type(byte_swap), bool)(byte_swap)

        field_type = self._parse_json_or_raw(str(row_map.get("type", "")))

        field_dict = {
            "name": name,
            "offset": offset,
            "size": size,
            "type": field_type,
            "scale": scale,
            "repeat": repeat,
            "description": description,
            "range_expression": range_expression,
            "enum_def_name": enum_def,
            "byte_swap": byte_swap,
        }

        # Run through sltcodec parser once for validation and normalization.
        validation_dict = field_dict.copy()
        for field_name in ("offset", "size"):
            value = validation_dict[field_name]
            if isinstance(value, InfoSize):
                validation_dict[field_name] = self._infosize_to_json_data(value)
        normalized = FieldDef.from_dict(validation_dict).to_dict()
        normalized["offset"] = offset
        normalized["size"] = size
        return normalized

    # The first argument is intentionally overloaded so this helper can accept
    # either an editor instance or a raw enum value while keeping the call sites
    # simple.
    def _parse_enum_def_input(
        self,
        value: object | None = None,
        enum_def_dict: dict[str, dict] | None = None,
    ) -> object:
        """Parse an enum definition cell as an optional EnumDef dict."""
        editor = self if isinstance(self, StructDefDictEditor) else None
        if editor is not None:
            actual_value = value
        else:
            actual_value = self if value is None else value
            if (value is not None and enum_def_dict is None
                    and type(value) is dict):
                enum_def_dict = value
                actual_value = self

        if actual_value is None:
            return None

        text = str(actual_value).strip()
        if not text:
            return None

        if enum_def_dict is None:
            if editor is not None:
                enum_def_dict = editor.enum_def_dict
            else:
                enum_def_dict = StructDefDictEditor.enum_def_dict
        if enum_def_dict and text in enum_def_dict:
            return text

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "enum_def must be a JSON object with name, description, "
                "and values.") from exc

        if not isinstance(parsed, dict):
            raise ValueError("enum_def must be a JSON object or enum name.")
        if parsed.get("__type__", "EnumDef") != "EnumDef":
            raise ValueError("enum_def must have __type__ set to EnumDef.")

        name = str(parsed.get("name", "")).strip()
        if not name:
            raise ValueError("enum_def name cannot be empty.")
        return name

    @staticmethod
    def _parse_infosize_input(value: object) -> object:
        """Parse ``byte,bit`` input, preserving non-static expressions."""
        if isinstance(value, InfoSize):
            return value
        if isinstance(value, dict) and value.get("__type__") == "InfoSize":
            return InfoSize(int(value.get("byte", 0)), int(value.get("bit", 0)))
        text = str(value).strip()
        if not text:
            text = "0,0"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("__type__") == "InfoSize":
            return InfoSize(int(parsed.get("byte", 0)),
                            int(parsed.get("bit", 0)))
        parts = [part.strip() for part in text.split(",")]
        if len(parts) == 1:
            try:
                return InfoSize(int(parts[0]), 0)
            except ValueError:
                return text
        if len(parts) != 2:
            raise ValueError(f"expected byte,bit or an expression: {text}")
        try:
            byte, bit = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"expected integer byte,bit: {text}") from exc
        return InfoSize(byte, bit)

    @staticmethod
    def _infosize_to_json_data(value: InfoSize) -> dict:
        """Convert an InfoSize instance to its typed JSON dictionary."""
        return json.loads(value.serialize())
