"""Binary Editor Window."""
from __future__ import annotations

import csv
import json
import tkinter as tk
from importlib import import_module
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sltcalc import SAFE_FUNCS
from sltcodec import (StructLayout, TypeDict, decode, encode,
                      load_struct_layout, save_struct_layout)
from sltcore import InfoSize, bits_get, virtual_bytearray
from tkinterex import (ConfirmDialog, OperationCanceledError, SelectDialog,
                       run_with_progress, show_modal_window)
from treeviewex import TreeviewEx

if __package__:
    from ._infosize_utils import format_infosize
    from ._struct_instance_model import (field_instance_at_path,
                                         format_field_value, format_type,
                                         minimum_struct_size,
                                         replace_instance_field_value,
                                         replace_instance_value)
    from .lua_plugins import NO_LUA_PLUGINS, LuaPluginManager
    from .resources import (load_elf_layout, load_pcap_layout,
                            load_pcapng_layout, load_pe_layout)
else:
    lua_plugins_module = import_module("lua_plugins")
    LuaPluginManager = lua_plugins_module.LuaPluginManager
    NO_LUA_PLUGINS = lua_plugins_module.NO_LUA_PLUGINS
    format_infosize = import_module("_infosize_utils").format_infosize
    _model = import_module("_struct_instance_model")
    field_instance_at_path = _model.field_instance_at_path
    format_field_value = _model.format_field_value
    format_type = _model.format_type
    minimum_struct_size = _model.minimum_struct_size
    replace_instance_field_value = _model.replace_instance_field_value
    replace_instance_value = _model.replace_instance_value
    resources_module = import_module("resources")
    load_pcap_layout = resources_module.load_pcap_layout
    load_pcapng_layout = resources_module.load_pcapng_layout
    load_pe_layout = resources_module.load_pe_layout
    load_elf_layout = resources_module.load_elf_layout

SAFE_FUNCS.setdefault("InfoSize", InfoSize)

_OperationCanceledError = OperationCanceledError


class _NestedTreeviewEx(TreeviewEx):  # pylint: disable=too-many-ancestors
    """TreeviewEx whose cell validation also accepts nested (child) rows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_edit_started = None

    def is_valid_cell(self, cell_id_pair: tuple) -> bool:
        """Check whether a cell exists, including rows below the root."""
        row_id, column_id = cell_id_pair
        if not row_id or not self.exists(row_id):
            return False
        try:
            column_index = int(str(column_id)[1:]) - 1
        except ValueError:
            return False
        return 0 <= column_index < len(self["columns"])

    def on_double_click(self, event: tk.Event) -> str | None:
        """Record a cell after TreeviewEx has started its standard edit."""
        cell_id_pair = self.get_clicked_cell_id_pair(event)
        result = super().on_double_click(event)
        if result == "break" and self.on_edit_started is not None:
            self.on_edit_started(cell_id_pair)
        return result


class BinaryEditorWindow(tk.Toplevel):
    """Decode and encode a binary file using a selected StructDef."""

    BINARY_COLUMNS = ("offset", "hex", "name", "type", "value", "size")
    TREE_LEVEL_WIDTH = 20
    HEX_COLUMN_ID = "#2"
    VALUE_COLUMN_ID = "#5"
    SETTINGS_FILENAME = "setting.json"
    SETTINGS_SECTION = "BinaryEditor"
    BIN_DIR_KEY = "last_bin_dir"
    STRUCT_LAYOUT_DIR_KEY = "last_struct_layout_dir"

    def _decode_with_progress(
        self,
        struct_layout: StructLayout,
        data: bytearray | bytes,
        title: str = "Decoding...",
    ) -> object:
        """Decode with a visible progress bar when supported by sltcodec."""
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

    def _show_decode_error(self, error: BaseException) -> None:
        """Show a codec error using tkinterex's modal dialog."""
        dialog = ConfirmDialog(
            self,
            str(error),
            [("ok", "OK")],
        )
        dialog.title("Decode Error")
        dialog.show()

    def _plugin_manager(self):
        """Return the plugin manager for this application's plugins folder."""
        return getattr(self, "_lua_plugin_manager", NO_LUA_PLUGINS)

    def _encode_with_progress(
        self,
        struct_layout: StructLayout,
        struct_instance: object,
        buf: bytearray,
        title: str = "Encoding...",
    ) -> bytearray:
        """Encode with a visible progress bar when supported by sltcodec."""
        encoded_instance = self._plugin_manager().apply_encode(struct_instance)
        return run_with_progress(
            self,
            title,
            lambda progress_callback: encode(
                struct_layout,
                encoded_instance,
                buf,
                progress_callback=progress_callback,
            ),
        )

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
        input_data: bytearray | bytes | virtual_bytearray | None = None,
    ) -> None:
        super().__init__(parent)
        # Stay hidden while widgets are built to avoid a partial-render flicker.
        self.withdraw()
        self.apl_dir = Path(apl_dir) if apl_dir is not None else Path.cwd()
        self.data_dir = (Path(data_dir) if data_dir is not None else
                         self._load_dir_setting("data_dir") or Path.cwd())
        self.last_bin_dir = self._load_dir_setting(self.BIN_DIR_KEY)
        self.last_struct_layout_dir = self._load_dir_setting(
            self.STRUCT_LAYOUT_DIR_KEY)
        self.struct_layout_file: Path | None = None
        self.binary_file: Path | None = None
        # Mask binary file access when data is supplied by the caller.
        self._binary_file_masked = input_data is not None
        self.binary_data = (input_data
                            if input_data is not None else bytearray())
        self.struct_instance = None
        self.struct_layout = StructLayout(
            struct_def_name="",
            type_dict=TypeDict(),
        )
        self._lua_plugin_manager = LuaPluginManager(self.apl_dir / "plugins")
        self._raw_edit_row_id: str | None = None
        self._value_edit_row_id: str | None = None
        self._value_edit_original_text = ""
        self._instance_path_by_row_id: dict[str, tuple[int, ...]] = {}
        self.bytes_per_row = 4
        # Whether a masked child window should write its edits back on close.
        self._save_on_close = True

        self.title("Binary Viewer")
        self.geometry("1100x650")
        self._build_menu()
        self._build_ui()
        if input_data is not None:
            self._refresh_tree()
        self.deiconify()

    def _build_menu(self) -> None:
        """Build the File/Return and definition editor menus."""
        menubar = tk.Menu(self)
        # A masked child window returns to its caller instead of using File.
        if getattr(self, "_binary_file_masked", False):
            return_menu = tk.Menu(menubar, tearoff=False)
            return_menu.add_command(
                label="Return without saving",
                command=self._return_without_saving,
            )
            return_menu.add_command(
                label="Return with saving",
                command=self._return_with_saving,
            )
            menubar.add_cascade(label="Return", menu=return_menu)
        else:
            file_menu = tk.Menu(menubar, tearoff=False)
            file_menu.add_command(label="New Binary...",
                                  command=self._new_binary)
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
            file_menu.add_command(
                label="Export to CSV...",
                command=self._export_tree_to_csv,
            )
            file_menu.add_command(
                label="Export to JSON...",
                command=self._export_tree_to_json,
            )
            file_menu.add_separator()
            file_menu.add_command(label="Exit", command=self._exit)
            menubar.add_cascade(label="File", menu=file_menu)

        type_definition_menu = tk.Menu(menubar, tearoff=False)
        type_definition_menu.add_command(
            label="Open StructLayout...",
            command=self._open_struct_layout,
        )
        resource_menu = tk.Menu(type_definition_menu, tearoff=False)
        resource_menu.add_command(
            label="PCAP",
            command=lambda: self._load_struct_layout_resource(load_pcap_layout),
        )
        resource_menu.add_command(
            label="PCAPNG",
            command=lambda: self._load_struct_layout_resource(load_pcapng_layout
                                                              ),
        )
        resource_menu.add_command(
            label="PE",
            command=lambda: self._load_struct_layout_resource(load_pe_layout),
        )
        resource_menu.add_command(
            label="ELF",
            command=lambda: self._load_struct_layout_resource(load_elf_layout),
        )
        type_definition_menu.add_cascade(
            label="Load Resource",
            menu=resource_menu,
        )
        type_definition_menu.add_separator()
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

    def _exit(self) -> None:
        """Close the whole app for the top-level editor."""
        self.master.destroy()

    def _return_without_saving(self) -> None:
        """Close this window without writing edits back to the caller."""
        self._save_on_close = False
        self.destroy()

    def _return_with_saving(self) -> None:
        """Close this window and write edits back to the caller."""
        if getattr(self, "struct_instance", None) is not None:
            try:
                encoded = self._encode_with_progress(
                    self.struct_layout,
                    self.struct_instance,
                    bytearray(),
                )
            except _OperationCanceledError:
                return
            except (TypeError, ValueError) as exc:
                messagebox.showerror("Encode Error", str(exc), parent=self)
                return
            if isinstance(self.binary_data, virtual_bytearray):
                if len(encoded) != len(self.binary_data):
                    messagebox.showerror(
                        "Encode Error",
                        "Encoded data must keep the original length.",
                        parent=self,
                    )
                    return
                self.binary_data.write_slice(0, encoded)
            else:
                self.binary_data[:] = encoded
        self._save_on_close = True
        self.destroy()

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

        ttk.Style(self).configure("Binary.Treeview", font="TkFixedFont")
        self.tree = _NestedTreeviewEx(
            self,
            columns=self.BINARY_COLUMNS,
            show="tree headings",
            selectmode="browse",
            style="Binary.Treeview",
        )
        self.tree.heading("#0", text="")
        for column in self.BINARY_COLUMNS:
            self.tree.heading(column, text=column)
        self.tree.column("#0", width=self.TREE_LEVEL_WIDTH, stretch=False)
        self.tree.column("offset", width=100, anchor=tk.W, stretch=False)
        self.tree.column("hex", width=220, anchor=tk.W, stretch=False)
        self.tree.column("name", width=180, anchor=tk.W)
        self.tree.column("type", width=140, anchor=tk.W)
        self.tree.column("value", width=260, anchor=tk.W)
        self.tree.column("size", width=80, anchor=tk.W, stretch=False)
        self._set_raw_columns(False)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.tree.on_edit_started = self._on_tree_edit_started
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
        self.tree.bind("<Button-3>", self._on_tree_right_click, add="+")

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

    def _load_dir_setting(self, key: str) -> Path | None:
        """Return the directory stored in apl_dir/setting.json, if any."""
        settings_file = self._settings_file()
        if not settings_file.is_file():
            return None
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            directory = settings.get(self.SETTINGS_SECTION, {}).get(key)
        except (OSError, ValueError, AttributeError):
            return None
        return Path(directory) if directory else None

    def _initial_dir(self, key: str) -> str:
        """Return the first existing directory to start the dialog from."""
        for candidate in (getattr(self, key, None), self.data_dir):
            if candidate is not None and Path(candidate).is_dir():
                return str(candidate)
        return str(Path.cwd())

    def _remember_data_dir(self, path: str, key: str | None = None) -> None:
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
        section = settings.setdefault(self.SETTINGS_SECTION, {})
        # '/' avoids '\\' being misread as an escape sequence in JSON.
        section["data_dir"] = selected_dir.as_posix()
        if key is not None:
            section[key] = selected_dir.as_posix()
            setattr(self, key, selected_dir)
        try:
            self.apl_dir.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(settings, indent=2),
                                     encoding="utf-8")
        except OSError:
            pass

    def _open_struct_layout(self) -> None:
        path = filedialog.askopenfilename(
            title="Open StructLayout JSON",
            initialdir=self._initial_dir(self.STRUCT_LAYOUT_DIR_KEY),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path, self.STRUCT_LAYOUT_DIR_KEY)

        try:
            struct_layout = load_struct_layout(path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror(
                "Open Error",
                str(exc),
                parent=self,
            )
            return

        self._activate_struct_layout(struct_layout, Path(path))

    def _load_struct_layout_resource(self, loader) -> None:
        """Load and activate a bundled StructLayout resource."""
        try:
            struct_layout = loader()
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Load Error", str(exc), parent=self)
            return
        self._activate_struct_layout(struct_layout, None)

    def _activate_struct_layout(
        self,
        struct_layout: StructLayout,
        source_path: Path | None,
    ) -> None:
        """Validate, decode, and display a loaded StructLayout."""

        default_key = struct_layout.struct_def_name
        if default_key not in struct_layout.type_dict.struct_dict:
            struct_layout.struct_def_name = ""
        struct_key = struct_layout.struct_def_name
        try:
            struct_instance = (self._decode_with_progress(
                struct_layout,
                self.binary_data,
            ) if struct_key and self.binary_data else None)
        except _OperationCanceledError:
            return
        except (TypeError, ValueError, NameError, SyntaxError) as exc:
            self._show_decode_error(exc)
            return

        self.struct_layout_file = source_path
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
            initialdir=self._initial_dir(self.STRUCT_LAYOUT_DIR_KEY),
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path, self.STRUCT_LAYOUT_DIR_KEY)
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
            struct_instance = (self._decode_with_progress(
                self.struct_layout,
                self.binary_data,
            ) if self.binary_data else None)
        except _OperationCanceledError:
            return
        except (TypeError, ValueError, NameError, SyntaxError) as exc:
            self._show_decode_error(exc)
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
            struct_instance = self._decode_with_progress(
                self.struct_layout,
                self.binary_data,
            )
        except _OperationCanceledError:
            return
        except (TypeError, ValueError, NameError, SyntaxError) as exc:
            self._show_decode_error(exc)
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
            minimum_size = minimum_struct_size(struct_def)
            binary_data = bytearray(minimum_size)
            self.struct_layout.struct_def_name = struct_key
            struct_instance = self._decode_with_progress(
                self.struct_layout,
                binary_data,
            )
        except _OperationCanceledError:
            return
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

    def _open_binary(self) -> None:
        self._ensure_struct_layout()
        struct_key = self.struct_layout.struct_def_name or (
            self._select_struct()
            if self.struct_layout.type_dict.struct_dict else None)

        path = filedialog.askopenfilename(
            title="Open binary file",
            initialdir=self._initial_dir(self.BIN_DIR_KEY),
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path, self.BIN_DIR_KEY)

        try:
            binary_data = bytearray(Path(path).read_bytes())
            if struct_key is not None:
                self.struct_layout.struct_def_name = struct_key
            else:
                self.struct_layout.struct_def_name = ""
            struct_instance = (self._decode_with_progress(
                self.struct_layout,
                binary_data,
            ) if struct_key is not None else None)
        except _OperationCanceledError:
            return
        except (OSError, TypeError, ValueError, NameError, SyntaxError) as exc:
            self._show_decode_error(exc)
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
            initialdir=self._initial_dir(self.BIN_DIR_KEY),
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        self._remember_data_dir(path, self.BIN_DIR_KEY)
        self._write_binary(Path(path))

    def _write_binary(self, path: Path) -> None:
        try:
            encoded = (self._encode_with_progress(
                self.struct_layout,
                self.struct_instance,
                bytearray(),
            ) if self.struct_instance is not None else bytearray(
                self.binary_data))
            path.write_bytes(bytes(encoded))
            self.binary_data = bytearray(encoded)
        except _OperationCanceledError:
            return
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Encode Error", str(exc), parent=self)
            return

        self.binary_file = path
        messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)

    def _export_tree_to_csv(self) -> None:
        """Export current tree rows to a CSV file (Excel compatible)."""
        path = filedialog.asksaveasfilename(
            title="Export Tree to CSV",
            initialdir=self._initial_dir(self.BIN_DIR_KEY),
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        rows = self._collect_tree_rows_for_export()
        if not rows:
            messagebox.showerror(
                "No Data",
                "No rows to export.",
                parent=self,
            )
            return

        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                header = ("level", "path", *self.BINARY_COLUMNS)
                writer.writerow(header)
                writer.writerows(rows)
            self._remember_data_dir(path, self.BIN_DIR_KEY)
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc), parent=self)
            return

        messagebox.showinfo("Exported", f"Exported to:\n{path}", parent=self)

    def _collect_tree_rows_for_export(self) -> list[tuple[str | int, ...]]:
        """Flatten the tree into rows with nesting level and path."""
        rows: list[tuple[str | int, ...]] = []

        def walk(parent_id: str, level: int, path_prefix: str) -> None:
            for row_id in self.tree.get_children(parent_id):
                values = tuple(self.tree.item(row_id, "values"))
                padded = values + ("", ) * (len(self.BINARY_COLUMNS) -
                                            len(values))
                name = str(padded[2]).strip() or str(row_id)
                path = name if not path_prefix else f"{path_prefix}.{name}"
                rows.append((level, path, *padded[:len(self.BINARY_COLUMNS)]))
                walk(row_id, level + 1, path)

        walk("", 0, "")
        return rows

    def _export_tree_to_json(self) -> None:
        """Export current tree rows to a nested JSON file."""
        path = filedialog.asksaveasfilename(
            title="Export Tree to JSON",
            initialdir=self._initial_dir(self.BIN_DIR_KEY),
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        nodes = self._collect_tree_nodes_for_json()
        if not nodes:
            messagebox.showerror(
                "No Data",
                "No rows to export.",
                parent=self,
            )
            return

        payload = {
            "columns": ["level", "path", *self.BINARY_COLUMNS],
            "rows": nodes,
        }
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._remember_data_dir(path, self.BIN_DIR_KEY)
        except OSError as exc:
            messagebox.showerror("Export Error", str(exc), parent=self)
            return

        messagebox.showinfo("Exported", f"Exported to:\n{path}", parent=self)

    def _collect_tree_nodes_for_json(self) -> list[dict[str, object]]:
        """Collect nested tree nodes with level/path and column values."""
        nodes: list[dict[str, object]] = []

        def walk(
            parent_id: str,
            level: int,
            path_prefix: str,
        ) -> list[dict[str, object]]:
            children_nodes: list[dict[str, object]] = []
            for row_id in self.tree.get_children(parent_id):
                values = tuple(self.tree.item(row_id, "values"))
                padded = values + ("", ) * (len(self.BINARY_COLUMNS) -
                                            len(values))
                name = str(padded[2]).strip() or str(row_id)
                path = name if not path_prefix else f"{path_prefix}.{name}"
                node = {
                    "level": level,
                    "path": path,
                    "offset": padded[0],
                    "hex": padded[1],
                    "name": padded[2],
                    "type": padded[3],
                    "value": padded[4],
                    "size": padded[5],
                    "children": walk(row_id, level + 1, path),
                }
                children_nodes.append(node)
            return children_nodes

        nodes.extend(walk("", 0, ""))
        return nodes

    def _refresh_tree(self) -> None:
        self._raw_edit_row_id = None
        self._value_edit_row_id = None
        self._instance_path_by_row_id = {}
        self.tree.delete(*self.tree.get_children())
        if self.struct_instance is not None:
            self._set_raw_columns(False)
            self.tree.column(
                "#0",
                width=self.TREE_LEVEL_WIDTH *
                self._instance_tree_depth(self.struct_instance),
            )
            self._insert_instance(self.struct_instance, "", InfoSize())
        else:
            self._set_raw_columns(True)
            self.tree.column("#0", width=self.TREE_LEVEL_WIDTH)
            self._insert_raw_bytes()

    @classmethod
    def _instance_tree_depth(cls, instance: object) -> int:
        """Return the number of visible Treeview indentation levels."""
        depth = 1
        for field_instance in instance.field_instances:
            if hasattr(field_instance.value, "field_instances"):
                depth = max(
                    depth,
                    1 + cls._instance_tree_depth(field_instance.value),
                )
        return depth

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
                    f"{offset},0",
                    " ".join(f"{value:02X}" for value in values),
                    "",
                    "",
                    "",
                    f"{len(values)},0",
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
        if isinstance(self.binary_data, virtual_bytearray):
            self.binary_data.write_slice(offset, values)
        else:
            self.binary_data[offset:offset + byte_count] = values

    def _on_tree_edit_started(self, cell: tuple[str, str]) -> None:
        """Track the cell opened by TreeviewEx's standard edit behavior."""
        if cell[1] == self.HEX_COLUMN_ID and cell[0].startswith("raw-"):
            self._raw_edit_row_id = cell[0]
        elif (cell[1] == self.VALUE_COLUMN_ID
              and cell[0] in self._instance_path_by_row_id):
            self._value_edit_row_id = cell[0]
            self._value_edit_original_text = self.tree.get_cell_value(cell)

    def _on_tree_right_click(self, event: tk.Event) -> None:
        """Show a context menu for bytearray fields under the hex column."""
        row_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if column_id != self.HEX_COLUMN_ID:
            return
        field_path = self._instance_path_by_row_id.get(row_id)
        if field_path is None:
            return
        field_instance = field_instance_at_path(
            self.struct_instance,
            field_path,
        )
        if format_type(field_instance.field_def.type) != "bytearray":
            return
        menu = tk.Menu(self.tree, tearoff=False)
        menu.add_command(
            label="Open BinaryEditorWindow",
            command=lambda: self._open_bytearray_field_editor(field_path),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _open_bytearray_field_editor(self, field_path: tuple[int, ...]) -> None:
        """Edit a bytearray field's bytes in a modal BinaryEditorWindow.

        decode() yields immutable bytes for bytearray fields, so the edited
        bytes are written back into the caller's struct instance on close.
        """
        field_instance = field_instance_at_path(
            self.struct_instance,
            field_path,
        )
        editable_data = bytearray(field_instance.value)
        editor = BinaryEditorWindow(
            self,
            apl_dir=self.apl_dir,
            data_dir=self.data_dir,
            input_data=editable_data,
        )
        show_modal_window(self, editor)
        if not editor._save_on_close:  # pylint: disable=protected-access
            return
        self.struct_instance = replace_instance_field_value(
            self.struct_instance,
            field_path,
            bytes(editable_data),
            self.struct_layout.type_dict,
        )
        self._update_instance_rows(self.struct_instance, "", InfoSize())

    def _on_value_edit_finished(self, event: tk.Event) -> None:
        row_id = self._value_edit_row_id
        if row_id is None or self.struct_instance is None:
            return
        self._value_edit_row_id = None
        text = event.widget.get()
        # Re-encoding and rebuilding the tree is costly, so skip no-op edits.
        if text == self._value_edit_original_text:
            return
        try:
            updated_instance = replace_instance_value(
                self.struct_instance,
                self._instance_path_by_row_id[row_id],
                text,
                self.struct_layout.type_dict,
            )
            self.struct_instance = updated_instance
        except _OperationCanceledError:
            return
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            messagebox.showerror("Value Error", str(exc), parent=self)
        self._update_instance_rows(self.struct_instance, "", InfoSize())

    def _insert_instance(
        self,
        instance: object,
        parent_id: str,
        base_offset: InfoSize,
        field_path: tuple[int, ...] = (),
        values_editable: bool = True,
    ) -> None:
        for field_index, field_instance in enumerate(instance.field_instances):
            field_def = field_instance.field_def
            offset = base_offset + field_def.offset
            row_id = self.tree.insert(
                parent_id,
                tk.END,
                values=self._row_values(field_instance, offset),
                open=True,
            )
            current_path = field_path + (field_index, )
            self._instance_path_by_row_id[row_id] = current_path
            if not values_editable:
                self.tree.set_readonly_cell(
                    (row_id, self.VALUE_COLUMN_ID),
                    True,
                )
            if hasattr(field_instance.value, "field_instances"):
                has_display_value = hasattr(field_instance.value,
                                            "display_value")
                if not has_display_value:
                    self.tree.set_readonly_cell(
                        (row_id, self.VALUE_COLUMN_ID),
                        True,
                    )
                self._insert_instance(
                    field_instance.value,
                    row_id,
                    offset,
                    current_path,
                    values_editable=values_editable and not has_display_value,
                )

    def _update_instance_rows(
        self,
        instance: object,
        parent_id: str,
        base_offset: InfoSize,
    ) -> None:
        """Refresh row values in place, keeping the existing tree structure."""
        for row_id, field_instance in zip(
                self.tree.get_children(parent_id),
                instance.field_instances,
        ):
            offset = base_offset + field_instance.field_def.offset
            self.tree.item(
                row_id,
                values=self._row_values(field_instance, offset),
            )
            if hasattr(field_instance.value, "field_instances"):
                self._update_instance_rows(
                    field_instance.value,
                    row_id,
                    offset,
                )

    def _row_values(
        self,
        field_instance: object,
        offset: InfoSize,
    ) -> tuple[str, ...]:
        field_def = field_instance.field_def
        size = field_def.size
        field_bytes = bits_get(self.binary_data, offset, size).to_bytes
        return (
            format_infosize(offset),
            field_bytes.hex(" ").upper(),
            field_def.name,
            format_type(field_def.type),
            format_field_value(field_instance, self.struct_layout.type_dict),
            format_infosize(size),
        )


def main() -> None:
    """Run the binary editor window."""
    root = tk.Tk()
    root.withdraw()
    editor = BinaryEditorWindow(root)
    editor.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
