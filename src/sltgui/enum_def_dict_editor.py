"""EnumDef Dict Editor Window."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk

from sltcodec import EnumDef, TypeDict
from tkinterex import EntryEx, TextEx, show_modal_window
from treeviewex import TreeviewEx

VALUE_COLUMNS = ("name", "value")


@dataclass(frozen=True)
class _ValueShift:
    """Data structure to hold enum value shift information."""
    sign: str
    amount: int


class EnumDefDictEditor(tk.Toplevel):
    """GUI editor for enum definitions in sltcodec type_dict JSON files."""

    def __init__(
        self,
        parent: tk.Misc,
        type_dict: TypeDict | None = None,
    ) -> None:
        """Initialize the EnumDefDictEditor with the given parent widget."""
        super().__init__(parent)
        # Stay hidden while widgets are built to avoid a partial-render flicker.
        self.withdraw()
        self.title("EnumDef Dict Editor")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = min(1100, max(640, screen_width - 80))
        window_height = min(680, max(420, screen_height - 100))
        # Position is left to show_modal_window(); setting it here too would
        # make the window visibly jump once show_modal_window repositions it.
        self.geometry(f"{window_width}x{window_height}")

        self.type_dict = type_dict if type_dict is not None else TypeDict()
        self.enum_data: dict[str, dict] = {
            key: enum_def.to_dict()
            for key, enum_def in self.type_dict.enum_dict.items()
        }
        self.current_enum_key: str | None = None

        self._build_ui()
        self._load_type_dict_data()

    def _build_ui(self) -> None:
        """Build the main UI layout."""
        self._build_button_bar()

        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, padding=8)
        right_frame = ttk.Frame(main_pane, padding=8)
        main_pane.add(left_frame, weight=1)
        main_pane.add(right_frame, weight=4)

        ttk.Label(left_frame, text="Enums").pack(anchor="w")
        left_btns = ttk.Frame(left_frame)
        left_btns.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(left_btns, text="Add Enum", command=self._add_enum).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(
            left_btns,
            text="Remove Enum",
            command=self._remove_enum,
        ).pack(side=tk.LEFT)

        self.enum_tree = TreeviewEx(
            left_frame,
            columns=("name", ),
            show="headings",
            selectmode="browse",
            height=25,
        )
        self.enum_tree.heading("name", text="Name")
        self.enum_tree.column("name", width=220, anchor=tk.W)
        self.enum_tree.set_readonly_column("#1")
        self.enum_tree.pack(fill=tk.BOTH, expand=True)
        self.enum_tree.bind("<<TreeviewSelect>>", self._on_enum_selected)

        meta_frame = ttk.LabelFrame(right_frame, text="Enum Meta", padding=8)
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
            command=self._update_enum_meta,
        ).grid(row=2, column=1, sticky="e", padx=(8, 0), pady=(8, 0))
        meta_frame.columnconfigure(1, weight=1)

        value_frame = ttk.LabelFrame(right_frame, text="Values", padding=8)
        value_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        value_btns = ttk.Frame(value_frame)
        value_btns.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(value_btns, text="Add Value", command=self._add_value).pack(
            side=tk.LEFT,
            padx=(0, 6),
        )
        ttk.Button(
            value_btns,
            text="Insert Value",
            command=self._insert_value,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            value_btns,
            text="Shift Value",
            command=self._shift_selected_values,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            value_btns,
            text="Remove Value",
            command=self._remove_value,
        ).pack(side=tk.LEFT)
        ttk.Label(value_btns, text="Start Value").pack(
            side=tk.LEFT,
            padx=(12, 4),
        )
        self.start_value_entry = EntryEx(value_btns, width=10)
        self.start_value_entry.value = "0"
        self.start_value_entry.pack(side=tk.LEFT)

        self.value_tree = TreeviewEx(
            value_frame,
            columns=VALUE_COLUMNS,
            show="headings",
            selectmode="extended",
            height=18,
        )
        self.value_tree.pack(fill=tk.BOTH, expand=True)
        for col in VALUE_COLUMNS:
            self.value_tree.heading(col, text=col)
        self.value_tree.column("name", width=240, anchor=tk.W)
        self.value_tree.column("value", width=180, anchor=tk.W)

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
        """Apply the edited enum definitions to the shared TypeDict."""
        if not self._flush_current_editor():
            return

        enum_dict = self.type_dict.enum_dict
        enum_dict.clear()
        enum_dict.update(self._to_enum_def_dict())
        self.destroy()

    def _load_type_dict_data(self) -> None:
        """Populate the editor from the current shared TypeDict."""
        self.current_enum_key = None
        self._refresh_enum_tree()

        enum_keys = list(self.enum_data.keys())
        if enum_keys:
            self._select_enum(enum_keys[0])
        else:
            self._clear_editor()

    def _to_enum_def_dict(self) -> dict[str, EnumDef]:
        """Convert the current enum_data to a dictionary of EnumDef objects."""
        return {
            key: EnumDef.from_dict(value)
            for key, value in self.enum_data.items()
        }

    def _refresh_enum_tree(self) -> None:
        """Refresh the enum_tree with the current enum_data."""
        self.enum_tree.delete(*self.enum_tree.get_children())
        for key in self.enum_data:
            self.enum_tree.insert("", tk.END, iid=key, values=(key, ))

    def _clear_editor(self) -> None:
        """Clear the editor fields and value tree."""
        self.name_entry.value = ""
        self.description_text.value = ""
        self.value_tree.delete(*self.value_tree.get_children())

    def _on_enum_selected(self, _event: tk.Event) -> None:
        """Handle the event when an enum is selected in the enum_tree."""
        selected = self.enum_tree.selection()
        if not selected:
            return

        new_key = selected[0]
        if self.current_enum_key == new_key:
            return

        if not self._flush_current_editor():
            return
        self._load_enum_to_editor(new_key)

    def _select_enum(self, key: str) -> None:
        """Select an enum in the enum_tree and load it into the editor."""
        if key not in self.enum_data:
            return
        self.enum_tree.selection_set(key)
        self.enum_tree.focus(key)
        self.enum_tree.see(key)
        self._load_enum_to_editor(key)

    def _load_enum_to_editor(self, key: str) -> None:
        """Load the enum data for the given key into the editor fields."""
        data = self.enum_data.get(key)
        if data is None:
            self._clear_editor()
            self.current_enum_key = None
            return

        self.current_enum_key = key
        self.name_entry.value = str(data.get("name", key))
        self.description_text.value = str(data.get("description", ""))

        self.value_tree.delete(*self.value_tree.get_children())
        for name, value in data.get("values", {}).items():
            self.value_tree.insert(
                "",
                tk.END,
                iid=f"value-{name}",
                values=(str(name), str(value)),
            )

    def _flush_current_editor(self) -> bool:
        """Flush the current editor data into the enum_data dictionary."""
        if self.current_enum_key is None:
            return True

        old_key = self.current_enum_key
        if old_key not in self.enum_data:
            self.current_enum_key = None
            return True

        new_name = self.name_entry.value.strip()
        if not new_name:
            messagebox.showerror(
                "Validation Error",
                "Enum name cannot be empty.",
            )
            return False

        if new_name != old_key and new_name in self.enum_data:
            messagebox.showerror(
                "Validation Error",
                f"Enum name '{new_name}' already exists.",
            )
            return False

        values: dict[str, int] = {}
        for row_id in self.value_tree.get_children():
            row_values = self.value_tree.item(row_id, "values")
            row_map = dict(zip(VALUE_COLUMNS, row_values))
            try:
                values.update(self._row_map_to_value_dict(row_map))
            except ValueError as exc:
                messagebox.showerror("Validation Error", str(exc))
                return False

        enum_dict = {
            "name": new_name,
            "description": self.description_text.value,
            "values": values,
        }

        if new_name != old_key:
            del self.enum_data[old_key]
            self.enum_data[new_name] = enum_dict
            self.current_enum_key = new_name
            self._refresh_enum_tree()
            self._select_enum(new_name)
        else:
            self.enum_data[old_key] = enum_dict
            self.enum_tree.item(old_key, values=(new_name, ))

        return True

    def _update_enum_meta(self) -> bool:
        """Update the metadata of the currently selected enum."""
        if self.current_enum_key is None:
            return False

        old_key = self.current_enum_key
        if old_key not in self.enum_data:
            return False

        new_name = self.name_entry.value.strip()
        if not new_name:
            messagebox.showerror(
                "Validation Error",
                "Enum name cannot be empty.",
            )
            return False

        if new_name != old_key and new_name in self.enum_data:
            messagebox.showerror(
                "Validation Error",
                f"Enum name '{new_name}' already exists.",
            )
            return False

        enum_dict = self.enum_data.pop(old_key)
        enum_dict["name"] = new_name
        enum_dict["description"] = self.description_text.value
        self.enum_data[new_name] = enum_dict
        self.current_enum_key = new_name
        self._refresh_enum_tree()
        self._select_enum(new_name)
        return True

    def _select_enum_tree_item(self, key: str) -> None:
        """Select an item in the enum_tree by its key.
        Parameters:
            key (str): The key of the enum to select.
        """
        self.enum_tree.selection_set(key)
        self.enum_tree.focus(key)
        self.enum_tree.see(key)

    def _add_enum(self) -> None:
        """Add a new enum to the enum_data and refresh the tree."""
        if not self._flush_current_editor():
            return

        base = "Enum"
        index = 1
        while f"{base}{index}" in self.enum_data:
            index += 1
        key = f"{base}{index}"
        start_value = self._read_start_value("Add Enum Error")
        if start_value is None:
            return

        self.enum_data[key] = {
            "name": key,
            "description": "",
            "values": {
                "VALUE_0": start_value,
            },
        }
        self._refresh_enum_tree()
        self._select_enum(key)

    def _remove_enum(self) -> None:
        """Remove the selected enum from the enum_data and refresh the tree."""
        selected = self.enum_tree.selection()
        if not selected:
            return

        key = selected[0]
        if key not in self.enum_data:
            return

        del self.enum_data[key]
        self.current_enum_key = None
        self._refresh_enum_tree()

        keys = list(self.enum_data.keys())
        if keys:
            self._select_enum(keys[0])
        else:
            self._clear_editor()

    def _add_value(self) -> None:
        """Add a new value to the currently selected enum."""
        if self.current_enum_key is None:
            messagebox.showerror("No Enum", "Please select an enum first.")
            return

        existing = self.value_tree.get_children()
        row_index = len(existing) + 1
        try:
            if existing:
                last_values = self.value_tree.item(existing[-1], "values")
                value = int(str(last_values[1]).strip(), 0) + 1
            else:
                value = self._read_start_value("Add Value Error")
                if value is None:
                    return
        except (IndexError, TypeError, ValueError) as exc:
            messagebox.showerror("Add Value Error", str(exc))
            return

        row_values = (f"VALUE_{row_index}", str(value))
        self.value_tree.insert(
            "",
            tk.END,
            iid=f"value-{row_index}",
            values=row_values,
        )

    def _insert_value(self) -> None:
        """Insert a value before the topmost selected value."""
        if self.current_enum_key is None:
            messagebox.showerror("No Enum", "Please select an enum first.")
            return

        existing = self.value_tree.get_children()
        selected = set(self.value_tree.selection())
        selected_index = next(
            (index
             for index, row_id in enumerate(existing) if row_id in selected),
            None,
        )
        if selected_index is None:
            messagebox.showerror(
                "No Value Selected",
                "Select a value to insert before.",
            )
            return

        if selected_index == 0:
            value = self._read_start_value("Insert Value Error")
            if value is None:
                return
        else:
            previous_values = self.value_tree.item(
                existing[selected_index - 1],
                "values",
            )
            try:
                value = int(str(previous_values[1]).strip(), 0) + 1
            except (IndexError, TypeError, ValueError) as exc:
                messagebox.showerror("Insert Value Error", str(exc))
                return

        row_index = len(existing) + 1
        row_values = (f"VALUE_{row_index}", str(value))
        self.value_tree.insert(
            "",
            selected_index,
            iid=f"value-{row_index}",
            values=row_values,
        )

    def _read_start_value(self, error_title: str) -> int | None:
        """Read and validate the configured first enum value."""
        start_value_entry = getattr(self, "start_value_entry", None)
        text = str(start_value_entry.value if start_value_entry else "0")
        try:
            return int(text.strip() or "0", 0)
        except ValueError as exc:
            messagebox.showerror(error_title, str(exc))
            return None

    def _shift_selected_values(self) -> None:
        """Shift all selected enum values by a signed amount."""
        selected = self.value_tree.selection()
        if not selected:
            messagebox.showerror(
                "No Values Selected",
                "Select at least one value first.",
            )
            return

        value_shift = self._ask_value_shift()
        if value_shift is None:
            return

        shift = value_shift.amount
        if value_shift.sign == "-":
            shift = -shift

        new_values: dict[str, str] = {}
        try:
            for row_id in selected:
                row_values = self.value_tree.item(row_id, "values")
                value = int(str(row_values[1]).strip(), 0) + shift
                new_values[row_id] = str(value)
        except (IndexError, TypeError, ValueError) as exc:
            messagebox.showerror("Shift Value Error", str(exc))
            return

        for row_id, value in new_values.items():
            row_values = list(self.value_tree.item(row_id, "values"))
            row_values[1] = value
            self.value_tree.item(row_id, values=row_values)

    def _ask_value_shift(self) -> _ValueShift | None:
        """Show the signed value-shift dialog."""
        dialog = tk.Toplevel(self)
        dialog.title("Shift Value")
        dialog.resizable(False, False)

        sign_var = tk.StringVar(value="+")
        ttk.Label(dialog, text="Sign").grid(
            row=0,
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
        ).grid(row=0, column=1, padx=(0, 12), pady=(12, 6))

        ttk.Label(dialog, text="Value").grid(
            row=1,
            column=0,
            padx=(12, 6),
            pady=6,
            sticky="w",
        )
        value_entry = EntryEx(dialog, width=12)
        value_entry.value = "0"
        value_entry.grid(row=1, column=1, padx=(0, 12), pady=6)

        result: list[_ValueShift | None] = [None]

        def apply_shift() -> None:
            try:
                amount = int(value_entry.value.strip() or "0", 0)
                if amount < 0:
                    raise ValueError("Shift value must be non-negative.")
                result[0] = _ValueShift(sign_var.get(), amount)
            except ValueError as exc:
                messagebox.showerror(
                    "Invalid Shift",
                    str(exc),
                    parent=dialog,
                )
                return
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply_shift).grid(
            row=2,
            column=0,
            padx=(12, 6),
            pady=(6, 12),
        )
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).grid(
            row=2,
            column=1,
            padx=(0, 12),
            pady=(6, 12),
        )
        value_entry.focus_set()
        show_modal_window(self, dialog)
        return result[0]

    def _remove_value(self) -> None:
        """Remove the selected values from the currently selected enum."""
        selected = self.value_tree.selection()
        if not selected:
            return
        for row_id in selected:
            self.value_tree.delete(row_id)

    @staticmethod
    def _row_map_to_value_dict(row_map: dict[str, object]) -> dict[str, int]:
        """Convert a row map to a dictionary of enum member name and value.
        Parameters:
            row_map (dict[str, object]): A dictionary representing a row
                with keys "name" and "value".
        Returns:
            dict[str, int]: A dictionary with the enum member name
                as the key and its integer value.
        Raises:
            ValueError: If the name is empty or the value is not
                a valid integer.
        """
        name = str(row_map.get("name", "")).strip()
        if not name:
            raise ValueError("Enum member name cannot be empty.")

        value_raw = str(row_map.get("value", "0")).strip() or "0"
        try:
            value = int(value_raw, 0)
        except ValueError as exc:
            raise ValueError(
                f"Invalid integer for enum member '{name}': {value_raw}"
            ) from exc

        return {name: value}
