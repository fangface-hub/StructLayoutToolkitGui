"""Editor for conditional packet payload StructLayout definitions."""
from __future__ import annotations

import tkinter as tk
from importlib import import_module
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sltcodec import StructLayout, TypeDict, load_struct_layout
from tkinterex import SelectDialog, show_modal_window
from treeviewex import TreeviewEx

if __package__:
    definitions_module = import_module("._payload_struct_defs", __package__)
else:
    definitions_module = import_module("_payload_struct_defs")
PayloadStructDef = definitions_module.PayloadStructDef
load_payload_struct_defs = definitions_module.load_payload_struct_defs
save_payload_struct_defs = definitions_module.save_payload_struct_defs


class PayloadStructDefEditor(tk.Toplevel):
    """Edit ordered condition and StructLayout pairs."""

    COLUMNS = ("condition", "struct")

    def __init__(
        self,
        parent: tk.Misc,
        definitions: list[PayloadStructDef] | None = None,
        *,
        data_dir: str | Path | None = None,
    ) -> None:
        """Initialize the payload struct definition editor."""
        super().__init__(parent)
        self.withdraw()
        self.title("Payload Struct Definition Editor")
        self.geometry("900x560")
        self.data_dir = Path(data_dir) if data_dir is not None else Path.cwd()
        self.definitions = definitions if definitions is not None else []
        self.definition_file: Path | None = None
        self.current_index: int | None = None
        self.updated = False
        self._build_menu()
        self._build_ui()
        self._refresh_tree()

    def _build_menu(self) -> None:
        """Build the menu bar for the editor."""
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Open...", command=self._open)
        file_menu.add_command(label="Save", command=self._save)
        file_menu.add_command(label="Save As...", command=self._save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        type_menu = tk.Menu(menubar, tearoff=False)
        type_menu.add_command(label="Select Struct...",
                              command=self._select_struct_definition)
        type_menu.add_separator()
        type_menu.add_command(label="Struct Definitions...",
                              command=self._open_struct_editor)
        type_menu.add_command(label="Enum Definitions...",
                              command=self._open_enum_editor)
        menubar.add_cascade(label="Type Definition", menu=type_menu)
        self.config(menu=menubar)

    def _build_ui(self) -> None:
        """Build the main user interface for the editor."""
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="Add", command=self._add).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Remove",
                   command=self._remove).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Move Up",
                   command=lambda: self._move(-1)).pack(side=tk.LEFT,
                                                        padx=(12, 0))
        ttk.Button(toolbar, text="Move Down",
                   command=lambda: self._move(1)).pack(side=tk.LEFT,
                                                       padx=(6, 0))

        self.tree = TreeviewEx(self,
                               columns=self.COLUMNS,
                               show="headings",
                               selectmode="browse")
        self.tree.heading("condition", text="Condition")
        self.tree.heading("struct", text="Struct")
        self.tree.column("condition", width=580, anchor=tk.W)
        self.tree.column("struct", width=220, anchor=tk.W)
        self.tree.set_readonly_column("#1", True)
        self.tree.set_readonly_column("#2", True)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=8)
        self.tree.bind("<<TreeviewSelect>>", self._on_selected)

        editor = ttk.LabelFrame(self, text="Selected definition", padding=8)
        editor.pack(fill=tk.X, padx=8, pady=8)
        ttk.Label(editor, text="Condition").grid(row=0, column=0, sticky=tk.W)
        self.condition_entry = ttk.Entry(editor)
        self.condition_entry.grid(row=0,
                                  column=1,
                                  columnspan=3,
                                  sticky=tk.EW,
                                  padx=(8, 0))
        ttk.Label(editor, text="Struct").grid(row=1,
                                              column=0,
                                              sticky=tk.W,
                                              pady=(8, 0))
        self.struct_combo = ttk.Combobox(editor, state="readonly")
        self.struct_combo.grid(row=1,
                               column=1,
                               sticky=tk.EW,
                               padx=(8, 0),
                               pady=(8, 0))
        ttk.Button(editor,
                   text="Load StructLayout...",
                   command=self._load_struct_layout).grid(row=1,
                                                          column=2,
                                                          padx=(8, 0),
                                                          pady=(8, 0))
        ttk.Button(editor, text="Update",
                   command=self._update).grid(row=1,
                                              column=3,
                                              padx=(8, 0),
                                              pady=(8, 0))
        editor.columnconfigure(1, weight=1)

    def _selected_definition(self) -> PayloadStructDef | None:
        """Return the currently selected payload struct definition,
           or None if no selection."""
        if self.current_index is None:
            return None
        if not 0 <= self.current_index < len(self.definitions):
            return None
        return self.definitions[self.current_index]

    def _refresh_tree(self, selected_index: int | None = None) -> None:
        """Refresh the tree view to reflect the current list
           of payload struct definitions."""
        self.tree.delete(*self.tree.get_children())
        for index, definition in enumerate(self.definitions):
            self.tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(definition.condition,
                        definition.struct_layout.struct_def_name),
            )
        if selected_index is not None and self.definitions:
            selected_index = min(selected_index, len(self.definitions) - 1)
            self.tree.selection_set(str(selected_index))
            self._load_editor(selected_index)
        elif not self.definitions:
            self.current_index = None
            self.condition_entry.delete(0, tk.END)
            self.struct_combo.configure(values=())
            self.struct_combo.set("")

    def _on_selected(self, _event: tk.Event) -> None:
        """Handle the event when a tree view item is selected."""
        selected = self.tree.selection()
        if selected:
            self._load_editor(int(selected[0]))

    def _load_editor(self, index: int) -> None:
        """Load the editor with the payload struct definition
           at the specified index."""
        self.current_index = index
        definition = self.definitions[index]
        self.condition_entry.delete(0, tk.END)
        self.condition_entry.insert(0, definition.condition)
        struct_names = list(definition.struct_layout.type_dict.struct_dict)
        self.struct_combo.configure(values=struct_names)
        self.struct_combo.set(definition.struct_layout.struct_def_name)

    def _add(self) -> None:
        """Add a new payload struct definition to the list
           and refresh the tree view."""
        self.definitions.append(
            PayloadStructDef("True", StructLayout("", TypeDict())))
        self.updated = True
        self._refresh_tree(len(self.definitions) - 1)

    def _remove(self) -> None:
        """Remove the currently selected payload struct definition
           from the list and refresh the tree view."""
        if self.current_index is None:
            return
        removed_index = self.current_index
        del self.definitions[removed_index]
        self.updated = True
        self._refresh_tree(removed_index)

    def _move(self, direction: int) -> None:
        """Move the currently selected payload struct definition
           up or down in the list and refresh the tree view."""
        if self.current_index is None:
            return
        target = self.current_index + direction
        if not 0 <= target < len(self.definitions):
            return
        self.definitions[self.current_index], self.definitions[target] = (
            self.definitions[target], self.definitions[self.current_index])
        self.updated = True
        self._refresh_tree(target)

    def _update(self) -> None:
        """Update the currently selected payload struct definition
           with the values from the editor."""
        definition = self._selected_definition()
        if definition is None:
            return
        condition = self.condition_entry.get().strip()
        if not condition:
            messagebox.showerror("Condition Error",
                                 "Condition is required.",
                                 parent=self)
            return
        definition.condition = condition
        definition.struct_layout.struct_def_name = self.struct_combo.get()
        self.updated = True
        self._refresh_tree(self.current_index)

    def _load_struct_layout(self) -> None:
        """Load a StructLayout from a JSON file and update the selected
           payload struct definition."""
        definition = self._selected_definition()
        if definition is None:
            return
        path = filedialog.askopenfilename(
            title="Open StructLayout JSON",
            initialdir=self.data_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            definition.struct_layout = load_struct_layout(path)
        except (OSError, TypeError, ValueError, NameError, SyntaxError) as exc:
            messagebox.showerror("Load Error", str(exc), parent=self)
            return
        self.data_dir = Path(path).parent
        self.updated = True
        self._refresh_tree(self.current_index)

    def _select_struct_definition(self) -> None:
        """Select the root StructDef for the selected payload definition."""
        definition = self._selected_definition()
        if definition is None:
            messagebox.showerror("No Definition",
                                 "Select a payload definition first.",
                                 parent=self)
            return
        struct_dict = definition.struct_layout.type_dict.struct_dict
        if not struct_dict:
            messagebox.showerror("No Struct",
                                 "No StructDef is available.",
                                 parent=self)
            return
        items = [(key, key) for key in sorted(struct_dict)]
        struct_key = SelectDialog(self, "Select StructDef", items).show()
        if struct_key is None:
            return
        definition.struct_layout.struct_def_name = struct_key
        self.updated = True
        self._refresh_tree(self.current_index)

    def _open_type_editor(self, module_name: str, class_name: str) -> None:
        """Open the type editor for the specified module and class,
           allowing the user to edit the type dictionary
           of the selected payload struct definition."""
        definition = self._selected_definition()
        if definition is None:
            messagebox.showerror("No Definition",
                                 "Select a payload definition first.",
                                 parent=self)
            return
        qualified_name = (f"{__package__}.{module_name}"
                          if __package__ else module_name)
        editor_class = getattr(import_module(qualified_name), class_name)
        editor = editor_class(self,
                              type_dict=definition.struct_layout.type_dict)
        show_modal_window(self, editor)
        self.updated = True
        self._refresh_tree(self.current_index)

    def _open_struct_editor(self) -> None:
        """Open the struct definition dictionary editor
           for the selected payload struct definition."""
        self._open_type_editor("struct_def_dict_editor", "StructDefDictEditor")

    def _open_enum_editor(self) -> None:
        """Open the enum definition dictionary editor
           for the selected payload struct definition."""
        self._open_type_editor("enum_def_dict_editor", "EnumDefDictEditor")

    def _open(self) -> None:
        """Open a JSON file containing payload struct definitions
           and load them into the editor."""
        path = filedialog.askopenfilename(
            title="Open Payload Struct Definitions",
            initialdir=self.data_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            definitions = load_payload_struct_defs(path)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("Open Error", str(exc), parent=self)
            return
        self.definitions[:] = definitions
        self.definition_file = Path(path)
        self.data_dir = self.definition_file.parent
        self.updated = True
        self._refresh_tree(0)

    def _save(self) -> None:
        """Save the current payload struct definitions to the existing file,
           prompting for a location if necessary."""
        if self.definition_file is None:
            self._save_as()
            return
        self._write(self.definition_file)

    def _save_as(self) -> None:
        """Prompt the user to save the current payload struct definitions
           to a new file."""
        path = filedialog.asksaveasfilename(
            title="Save Payload Struct Definitions",
            initialdir=self.data_dir,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._write(Path(path))

    def _write(self, path: Path) -> None:
        """Write the current payload struct definitions
           to the specified file path."""
        try:
            save_payload_struct_defs(self.definitions, path)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)
            return
        self.definition_file = path
        self.data_dir = path.parent
        messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)


def main() -> None:
    """Entry point for the payload struct definition editor application."""
    root = tk.Tk()
    root.withdraw()
    editor = PayloadStructDefEditor(root)
    show_modal_window(root, editor)
    root.destroy()


if __name__ == "__main__":
    main()
