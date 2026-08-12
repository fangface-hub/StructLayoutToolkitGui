"""Binary Editor Window."""
from __future__ import annotations

import json
import tkinter as tk
from ast import literal_eval
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sltcodec import (StructDef, StructLayout, TypeDict, decode, encode,
                      load_struct_layout, save_struct_layout)
from sltcore import InfoSize, bits_get
from tkinterex import SelectDialog, show_modal_window
from treeviewex import TreeviewEx


class BinaryEditorWindow(tk.Toplevel):
    """Decode and encode a binary file using a selected StructDef."""

    BINARY_COLUMNS = ("offset", "hex", "name", "type", "value", "size")
    HEX_COLUMN_ID = "#2"
    VALUE_COLUMN_ID = "#5"
    SETTINGS_FILENAME = "setting.json"

    def _ensure_struct_layout(self) -> None:
        """Ensure the current window has an active StructLayout object."""
        if not hasattr(self, "struct_layout") or self.struct_layout is None:
            self.struct_layout = StructLayout(
                struct_def_name="",
                type_dict=TypeDict(),
            )

    def __init__(
        self,
        parent: tk.Misc,
        apl_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        # Stay hidden while widgets are built to avoid a partial-render flicker.
        self.withdraw()
        self.apl_dir = Path(apl_dir) if apl_dir is not None else Path.cwd()
        self.data_dir = (Path(data_dir) if data_dir is not None else
                         self._load_data_dir_setting() or Path.cwd())
        self.struct_layout_file: Path | None = None
        self.binary_file: Path | None = None
        self.binary_data = bytearray()
        self.struct_instance = None
        self.struct_layout = StructLayout(
            struct_def_name="",
            type_dict=TypeDict(),
        )
        self._raw_edit_row_id: str | None = None
        self._value_edit_row_id: str | None = None
        self._instance_path_by_row_id: dict[str, tuple[int, ...]] = {}
        self.bytes_per_row = 4

        self.title("Binary Viewer")
        self.geometry("1100x650")
        self._build_menu()
        self._build_ui()
        self.deiconify()

    def _build_menu(self) -> None:
        """Build the File and definition editor menus."""
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Binary...", command=self._new_binary)
        file_menu.add_command(
            label="Open Binary...",
            command=self._open_binary,
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save Binary",
            command=self._save_binary,
        )
        file_menu.add_command(
            label="Save Binary As...",
            command=self._save_binary_as,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        type_definition_menu = tk.Menu(menubar, tearoff=False)
        type_definition_menu.add_command(
            label="Open StructLayout...",
            command=self._open_struct_layout,
        )
        type_definition_menu.add_command(
            label="Save StructLayout",
            command=self._save_struct_layout,
        )
        type_definition_menu.add_command(
            label="Save StructLayout As...",
            command=self._save_struct_layout_as,
        )
        type_definition_menu.add_separator()
        type_definition_menu.add_command(
            label="Select Struct...",
            command=self._select_struct_definition,
        )
        type_definition_menu.add_separator()
        type_definition_menu.add_command(
            label="Struct Definitions...",
            command=self._open_struct_definition_editor,
        )
        type_definition_menu.add_command(
            label="Enum Definitions...",
            command=self._open_enum_definition_editor,
        )
        menubar.add_cascade(
            label="Type Definition",
            menu=type_definition_menu,
        )
        self.config(menu=menubar)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)
        ttk.Label(toolbar, text="Bytes/row:").pack(side=tk.LEFT)
        self.bytes_per_row_combo = ttk.Combobox(
            toolbar,
            state="readonly",
            width=4,
            values=(1, 2, 4, 8, 16),
        )
        self.bytes_per_row_combo.set(str(self.bytes_per_row))
        self.bytes_per_row_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.bytes_per_row_combo.bind(
            "<<ComboboxSelected>>",
            self._on_bytes_per_row_changed,
        )
        self.struct_label = ttk.Label(toolbar, text="Struct: (none)")
        self.struct_label.pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Re-decode",
            command=self._redecode_binary,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.tree = TreeviewEx(
            self,
            columns=self.BINARY_COLUMNS,
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="")
        for column in self.BINARY_COLUMNS:
            self.tree.heading(column, text=column)
        self.tree.column("#0", width=20, stretch=False)
        self.tree.column("offset", width=100, anchor=tk.W, stretch=False)
        self.tree.column("hex", width=220, anchor=tk.W, stretch=False)
        self.tree.column("name", width=180, anchor=tk.W)
        self.tree.column("type", width=140, anchor=tk.W)
        self.tree.column("value", width=260, anchor=tk.W)
        self.tree.column("size", width=80, anchor=tk.W, stretch=False)
        self._set_raw_columns(False)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.tree.bind("<Double-1>", self._on_tree_double_click, add="+")
        self.tree.entry.bind(
            "<KeyRelease>",
            self._on_raw_hex_key_release,
            add="+",
        )
        self.tree.entry.bind(
            "<Return>",
            self._on_value_edit_finished,
            add="+",
        )
        self.tree.entry.bind(
            "<FocusOut>",
            self._on_value_edit_finished,
            add="+",
        )

    def _open_struct_definition_editor(self) -> None:
        """Open the StructDef editor in a modal child window."""
        module_name = self._editor_module_name("struct_def_dict_editor")
        editor_class = import_module(module_name).StructDefDictEditor
        editor = editor_class(
            self,
            type_dict=self.struct_layout.type_dict,
        )
        show_modal_window(self, editor)

    def _open_enum_definition_editor(self) -> None:
        """Open the EnumDef editor in a modal child window."""
        module_name = self._editor_module_name("enum_def_dict_editor")
        editor_class = import_module(module_name).EnumDefDictEditor
        editor = editor_class(
            self,
            type_dict=self.struct_layout.type_dict,
        )
        show_modal_window(self, editor)

    @staticmethod
    def _editor_module_name(editor_module: str) -> str:
        """Return the import name for package and script execution modes."""
        if __package__:
            return f"{__package__}.{editor_module}"
        return editor_module

    def _settings_file(self) -> Path:
        return self.apl_dir / self.SETTINGS_FILENAME

    def _load_data_dir_setting(self) -> Path | None:
        """Return the data_dir stored in apl_dir/setting.json, if any."""
        settings_file = self._settings_file()
        if not settings_file.is_file():
            return None
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            data_dir = settings.get("data_dir")
        except (OSError, ValueError, AttributeError):
            return None
        return Path(data_dir) if data_dir else None

    def _remember_data_dir(self, path: str) -> None:
        """Save the directory of the selected path as the new data_dir."""
        selected_dir = Path(path).parent
        self.data_dir = selected_dir
        settings_file = self._settings_file()
        settings = {}
        if settings_file.is_file():
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                settings = {}
        # '/' avoids '\\' being misread as an escape sequence in JSON.
        settings["data_dir"] = selected_dir.as_posix()
        try:
            self.apl_dir.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(settings, indent=2),
                                     encoding="utf-8")
        except OSError:
            pass

    def _open_struct_layout(self) -> None:
        path = filedialog.askopenfilename(
            title="Open StructLayout JSON",
            initialdir=str(self.data_dir),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path)

        try:
            struct_layout = load_struct_layout(path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror(
                "Open Error",
                str(exc),
                parent=self,
            )
            return

        default_key = struct_layout.struct_def_name
        if default_key not in struct_layout.type_dict.struct_dict:
            struct_layout.struct_def_name = ""
        struct_key = struct_layout.struct_def_name
        try:
            struct_instance = (decode(
                struct_layout,
                self.binary_data,
            ) if struct_key and self.binary_data else None)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Decode Error", str(exc), parent=self)
            return

        self.struct_layout_file = Path(path)
        self.struct_instance = struct_instance
        self.struct_layout = struct_layout
        label = (f"Struct: {struct_key}" if struct_key else "Struct: (none)")
        self.struct_label.configure(text=label)
        self._refresh_tree()

    def _save_struct_layout(self) -> None:
        self._ensure_struct_layout()
        if self.struct_layout_file is None:
            self._save_struct_layout_as()
            return
        self._write_struct_layout(self.struct_layout_file)

    def _save_struct_layout_as(self) -> None:
        self._ensure_struct_layout()
        path = filedialog.asksaveasfilename(
            title="Save StructLayout JSON",
            initialdir=str(self.data_dir),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path)
        self._write_struct_layout(Path(path))

    def _write_struct_layout(self, path: Path) -> None:
        try:
            save_struct_layout(self.struct_layout, path)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)
            return

        self.struct_layout_file = path
        messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)

    def _select_struct_definition(self) -> None:
        """Select a StructDef and re-decode the current binary data."""
        self._ensure_struct_layout()
        struct_key = (self._select_struct()
                      if self.struct_layout.type_dict.struct_dict else None)
        if struct_key is None:
            return

        try:
            self.struct_layout.struct_def_name = struct_key
            struct_instance = (decode(
                self.struct_layout,
                self.binary_data,
            ) if self.binary_data else None)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Decode Error", str(exc), parent=self)
            return

        self.struct_instance = struct_instance
        self.struct_label.configure(text=f"Struct: {struct_key}")
        self._refresh_tree()

    def _redecode_binary(self) -> None:
        """Re-decode the current binary using the active definitions."""
        self._ensure_struct_layout()
        struct_key = self.struct_layout.struct_def_name
        if not self.binary_data:
            messagebox.showerror(
                "No Data",
                "No binary data to decode.",
                parent=self,
            )
            return
        if struct_key not in self.struct_layout.type_dict.struct_dict:
            messagebox.showerror(
                "No Struct",
                "Select a valid StructDef before decoding.",
                parent=self,
            )
            return

        try:
            struct_instance = decode(self.struct_layout, self.binary_data)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Decode Error", str(exc), parent=self)
            return

        self.struct_instance = struct_instance
        self._refresh_tree()

    def _new_binary(self) -> None:
        """Create a zero-filled bytearray for a selected StructDef."""
        self._ensure_struct_layout()
        struct_key = self.struct_layout.struct_def_name or (
            self._select_struct()
            if self.struct_layout.type_dict.struct_dict else None)
        if struct_key is None:
            self.binary_data = bytearray()
            self.binary_file = None
            self.struct_instance = None
            self.struct_layout.struct_def_name = ""
            self.struct_label.configure(text="Struct: (none) - raw binary")
            self._refresh_tree()
            return

        struct_def = self.struct_layout.type_dict.struct_dict[struct_key]
        try:
            minimum_size = self._minimum_struct_size(struct_def)
            binary_data = bytearray(minimum_size)
            self.struct_layout.struct_def_name = struct_key
            struct_instance = decode(
                self.struct_layout,
                binary_data,
            )
        except (TypeError, ValueError) as exc:
            messagebox.showerror(
                "New Binary Error",
                str(exc),
                parent=self,
            )
            return

        self.binary_data = binary_data
        self.binary_file = None
        self.struct_instance = struct_instance
        self.struct_label.configure(text=f"Struct: {struct_key}")
        self._refresh_tree()

    @staticmethod
    def _minimum_struct_size(struct_def: StructDef) -> int:
        """Return the minimum byte length required by static field layouts."""
        minimum_size = InfoSize()
        for field_def in struct_def.fields:
            if not isinstance(field_def.offset, InfoSize):
                raise ValueError(
                    f"Field '{field_def.name}' has an offset expression.")
            if not isinstance(field_def.size, InfoSize):
                raise ValueError(
                    f"Field '{field_def.name}' has a size expression.")

            repeat = (field_def.repeat
                      if field_def.repeat and field_def.repeat > 1 else 1)
            field_end = field_def.offset + repeat * field_def.size
            if field_end > minimum_size:
                minimum_size = field_end
        return minimum_size.bytes

    def _open_binary(self) -> None:
        self._ensure_struct_layout()
        struct_key = self.struct_layout.struct_def_name or (
            self._select_struct()
            if self.struct_layout.type_dict.struct_dict else None)

        path = filedialog.askopenfilename(
            title="Open binary file",
            initialdir=str(self.data_dir),
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path)

        try:
            binary_data = bytearray(Path(path).read_bytes())
            if struct_key is not None:
                self.struct_layout.struct_def_name = struct_key
            else:
                self.struct_layout.struct_def_name = ""
            struct_instance = (decode(
                self.struct_layout,
                binary_data,
            ) if struct_key is not None else None)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Decode Error", str(exc), parent=self)
            return

        self.binary_file = Path(path)
        self.binary_data = binary_data
        self.struct_instance = struct_instance
        label = (f"Struct: {struct_key}"
                 if struct_key else "Struct: (none) - raw binary")
        self.struct_label.configure(text=label)
        self._refresh_tree()

    def _select_struct(self) -> str | None:
        items = [(key, key)
                 for key in sorted(self.struct_layout.type_dict.struct_dict)]
        dialog = SelectDialog(self, "Select StructDef", items)
        return dialog.show()

    def _save_binary(self) -> None:
        self._ensure_struct_layout()
        if self.binary_file is None:
            self._save_binary_as()
            return
        self._write_binary(self.binary_file)

    def _save_binary_as(self) -> None:
        self._ensure_struct_layout()
        if self.struct_instance is None and not self.binary_data:
            messagebox.showerror("No Data",
                                 "No binary data to save.",
                                 parent=self)
            return

        path = filedialog.asksaveasfilename(
            title="Save binary file",
            initialdir=str(self.data_dir),
            defaultextension=".bin",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path)
        self._write_binary(Path(path))

    def _write_binary(self, path: Path) -> None:
        try:
            encoded = (encode(
                self.struct_layout,
                self.struct_instance,
                bytearray(),
            ) if self.struct_instance is not None else bytearray(
                self.binary_data))
            path.write_bytes(bytes(encoded))
            self.binary_data = bytearray(encoded)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Encode Error", str(exc), parent=self)
            return

        self.binary_file = path
        messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)

    def _refresh_tree(self) -> None:
        self._raw_edit_row_id = None
        self._value_edit_row_id = None
        self._instance_path_by_row_id = {}
        self.tree.delete(*self.tree.get_children())
        if self.struct_instance is not None:
            self._set_raw_columns(False)
            self._insert_instance(self.struct_instance, "", InfoSize())
        else:
            self._set_raw_columns(True)
            self._insert_raw_bytes()

    def _on_bytes_per_row_changed(self, _event: tk.Event) -> None:
        self.bytes_per_row = int(self.bytes_per_row_combo.get())
        if self.struct_instance is None:
            self._refresh_tree()

    def _set_raw_columns(self, raw_mode: bool) -> None:
        for column_id in ("#1", "#3", "#4", "#6"):
            self.tree.set_readonly_column(column_id, True)
        self.tree.set_readonly_column(self.HEX_COLUMN_ID, not raw_mode)
        self.tree.set_readonly_column(self.VALUE_COLUMN_ID, raw_mode)

    def _insert_raw_bytes(self) -> None:
        for offset in range(0, len(self.binary_data), self.bytes_per_row):
            values = self.binary_data[offset:offset + self.bytes_per_row]
            self.tree.insert(
                "",
                tk.END,
                iid=f"raw-{offset}",
                values=(
                    f"0x{offset:X}",
                    " ".join(f"{value:02X}" for value in values),
                    "",
                    "",
                    "",
                    f"{len(values)}B",
                ),
            )

    def _on_raw_hex_key_release(self, _event: tk.Event) -> None:
        if self.struct_instance is not None:
            return
        row_id = self._raw_edit_row_id
        if row_id is None:
            return
        if not row_id.startswith("raw-"):
            return
        text = self.tree.entry.get().strip()
        hex_text = text.replace(" ", "")
        offset = int(row_id[4:])
        byte_count = min(self.bytes_per_row, len(self.binary_data) - offset)
        if len(hex_text) != byte_count * 2:
            return
        try:
            values = bytes.fromhex(hex_text)
        except ValueError:
            return
        self.binary_data[offset:offset + byte_count] = values

    def _on_tree_double_click(self, event: tk.Event) -> None:
        cell = self.tree.get_clicked_cell_id_pair(event)
        if cell[1] == self.HEX_COLUMN_ID and cell[0].startswith("raw-"):
            self._raw_edit_row_id = cell[0]
        elif (cell[1] == self.VALUE_COLUMN_ID
              and cell[0] in self._instance_path_by_row_id):
            self._value_edit_row_id = cell[0]

    def _on_value_edit_finished(self, event: tk.Event) -> None:
        row_id = self._value_edit_row_id
        if row_id is None or self.struct_instance is None:
            return
        self._value_edit_row_id = None
        try:
            updated_instance = self._replace_instance_value(
                self.struct_instance,
                self._instance_path_by_row_id[row_id],
                event.widget.get(),
                self.struct_layout.type_dict,
            )
            encoded = encode(
                self.struct_layout,
                updated_instance,
                bytearray(self.binary_data),
            )
            self.binary_data = bytearray(encoded)
            self.struct_instance = decode(self.struct_layout, self.binary_data)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            messagebox.showerror("Value Error", str(exc), parent=self)
        self._refresh_tree()

    @classmethod
    def _replace_instance_value(
        cls,
        instance: object,
        field_path: tuple[int, ...],
        text: str,
        type_dict: TypeDict,
    ) -> object:
        field_index = field_path[0]
        field_instances = list(instance.field_instances)
        field_instance = field_instances[field_index]
        if len(field_path) == 1:
            value = cls._parse_value(text, field_instance.value)
            updated_field_instance = field_instance.with_value(
                value,
                type_dict,
            )
        else:
            value = cls._replace_instance_value(
                field_instance.value,
                field_path[1:],
                text,
                type_dict,
            )
            updated_field_instance = field_instance.with_value(
                value,
                type_dict,
            )
        field_instances[field_index] = updated_field_instance
        return replace(instance, field_instances=field_instances)

    @staticmethod
    def _parse_value(text: str, current_value: object) -> object:
        if isinstance(current_value, bool):
            values = {"true": True, "false": False, "1": True, "0": False}
            try:
                return values[text.strip().lower()]
            except KeyError as exc:
                raise ValueError(
                    "Boolean value must be true or false.") from exc
        if isinstance(current_value, int):
            try:
                return int(text, 0)
            except ValueError:
                return int(text, 10)
        if isinstance(current_value, float):
            return float(text)
        if isinstance(current_value, bytes):
            return bytes.fromhex(text)
        if isinstance(current_value, bytearray):
            return bytearray.fromhex(text)
        if isinstance(current_value, str):
            return text
        parsed = literal_eval(text)
        if not isinstance(parsed, type(current_value)):
            raise ValueError(f"Value must be {type(current_value).__name__}.")
        return parsed

    def _insert_instance(
            self,
            instance: object,
            parent_id: str,
            base_offset: InfoSize,
            field_path: tuple[int, ...] = (),
    ) -> None:
        for field_index, field_instance in enumerate(instance.field_instances):
            field_def = field_instance.field_def
            offset = base_offset + field_def.offset
            size = field_def.size
            field_bytes = bits_get(self.binary_data, offset, size).to_bytes
            row_id = self.tree.insert(
                parent_id,
                tk.END,
                values=(
                    self._format_offset(offset),
                    field_bytes.hex(" ").upper(),
                    field_def.name,
                    self._format_type(field_def.type),
                    self._format_value(field_instance.value),
                    self._format_size(size),
                ),
                open=True,
            )
            current_path = field_path + (field_index, )
            self._instance_path_by_row_id[row_id] = current_path
            if hasattr(field_instance.value, "field_instances"):
                self.tree.set_readonly_cell(
                    (row_id, self.VALUE_COLUMN_ID),
                    True,
                )
                self._insert_instance(
                    field_instance.value,
                    row_id,
                    offset,
                    current_path,
                )

    @staticmethod
    def _format_offset(offset: InfoSize) -> str:
        if offset.bit:
            return f"0x{offset.byte:X}:{offset.bit}"
        return f"0x{offset.byte:X}"

    @staticmethod
    def _format_size(size: InfoSize) -> str:
        return f"{size.byte},{size.bit}"

    @staticmethod
    def _format_type(field_type: object) -> str:
        if isinstance(field_type, StructDef):
            return field_type.name or "StructDef"
        return str(field_type)

    @staticmethod
    def _format_value(value: object) -> str:
        if hasattr(value, "field_instances"):
            return "<StructInstance>"
        if isinstance(value, (bytes, bytearray)):
            return value.hex(" ").upper()
        return str(value)


def main() -> None:
    """Run the binary editor window."""
    root = tk.Tk()
    root.withdraw()
    editor = BinaryEditorWindow(root)
    editor.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
