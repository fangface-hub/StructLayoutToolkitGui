# StructLayoutToolkitGui

StructLayoutToolkitGui is a desktop application for inspecting and editing
binary files using structure layouts defined by the StructLayoutToolkit
ecosystem. It combines a hierarchical binary viewer with editors for structure
and enumeration definitions.

## Features

- Decode binary files with a selected `StructDef`.
- Display field offsets, raw bytes, names, types, values, and sizes.
- Inspect nested structures in a hierarchical tree view.
- Edit decoded field values and encode them back to binary data.
- View and edit raw hexadecimal data when no structure is selected.
- Create and edit `StructDef` and `EnumDef` dictionaries.
- Re-decode loaded data after changing type definitions.
- Open, save, and save-as both binary and StructLayout files.
- Configure the number of bytes shown per row in raw mode.

## Requirements

- Python 3.14 or later
- Tkinter support in the Python installation

Tkinter is included with standard Python installations on Windows and macOS.
Some Linux distributions provide it as a separate system package.

## Installation

Install the package from PyPI:

```console
python -m pip install sltgui
```

## Running the Application

Start the binary editor with:

```console
python -m sltgui.binary_editor_window
```

## Basic Workflow

1. Open a StructLayout JSON file from **Type Definition > Open StructLayout**.
2. Open a binary file from **File > Open Binary**.
3. Double-click a value cell to edit a decoded field.
4. Use **Re-decode** after updating Struct or Enum definitions.
5. Save changes with **Save Binary** or choose a new destination with **Save Binary As**.

The files may also be opened in the opposite order. A binary opened without a
layout is shown in raw mode and is decoded when a valid StructLayout is loaded.

Static offsets and sizes use `byte,bit` notation. For example, `4,0` represents
four bytes and `0,3` represents three bits.

## Using the Window from Python

The GUI classes are also available as a Python API:

```python
import tkinter as tk

from sltgui import BinaryEditorWindow

root = tk.Tk()
root.withdraw()
window = BinaryEditorWindow(root)
window.protocol("WM_DELETE_WINDOW", root.destroy)
root.mainloop()
```

The package exports `BinaryEditorWindow`, `StructDefDictEditor`, and
`EnumDefDictEditor`.

## Related Projects

StructLayoutToolkitGui uses the following StructLayoutToolkit packages:

- `sltcore` for core structure and size types
- `sltcodec` for StructLayout serialization and binary encoding/decoding
- `sltcalc` for expression evaluation

## Links

- [Source code](https://github.com/fangface-hub/StructLayoutToolkitGui)
- [Issue tracker](https://github.com/fangface-hub/StructLayoutToolkitGui/issues)
- [Developer documentation](https://github.com/fangface-hub/StructLayoutToolkitGui/blob/main/README.md)

## License

StructLayoutToolkitGui is distributed under the MIT License.
