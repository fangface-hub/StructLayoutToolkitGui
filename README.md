# StructLayoutToolkitGui

StructLayoutToolkitGui is a Tkinter application for viewing and editing binary
data using structure layouts defined with StructLayoutToolkit. It also provides
GUI editors for structure and enumeration definitions.

## Development Environment

- Python 3.14 or later
- [uv](https://docs.astral.sh/uv/)
- A Python environment with Tkinter support

The project depends on SltCore for structure definitions, SltCodec for encoding
and decoding, and SltCalc for expression evaluation. See `pyproject.toml` for
the exact version requirements.

### Setup

```powershell
git clone https://github.com/fangface-hub/StructLayoutToolkitGui.git
Set-Location StructLayoutToolkitGui
uv sync
```

### Run

```powershell
uv run python -m sltgui.binary_editor_window
```

### Test

Run the complete test suite:

```powershell
uv run pytest -q
```

To run a specific test file:

```powershell
uv run pytest tests/test_binary_editor_window.py -q
```

## Source Layout

| Path | Responsibility |
| --- | --- |
| `src/sltgui/binary_editor_window.py` | Main window for opening, decoding, editing, encoding, and saving binary data |
| `src/sltgui/struct_def_dict_editor.py` | Modal editor for the `StructDef` dictionary |
| `src/sltgui/enum_def_dict_editor.py` | Modal editor for the `EnumDef` dictionary |
| `src/sltgui/__init__.py` | Public API with lazy imports for the GUI classes |
| `tests/` | Unit tests with GUI dependencies replaced by stubs |

The package exposes three public classes:

```python
from sltgui import BinaryEditorWindow, EnumDefDictEditor, StructDefDictEditor
```

## Data Flow

1. Load a `StructLayout` JSON file to obtain its `TypeDict` and selected `StructDef`.
2. Pass the binary data to `decode()` to create a `StructInstance`.
3. Render `StructInstance.field_instances` in the tree view.
4. When a value is edited, convert its text back to the original value type and create a new field with `FieldInstance.with_value()`.
5. Pass the updated instance to `encode()`, then call `decode()` again to keep the display and derived data synchronized.

The `Update` action in the Struct and Enum definition editors updates the shared
`TypeDict`, but it does not automatically rebuild an existing `StructInstance`.
Use `Re-decode` in the main window after changing definitions.

## Implementation Notes

### Updating Instances

`FieldInstance` is immutable. Replacing only its value with
`dataclasses.replace()` can leave derived data such as `enum_item` out of date.
Always use `FieldInstance.with_value(value, type_dict)` when changing a value.

For nested structures, rebuild each object from the target `FieldInstance` up
to the parent `StructInstance`. See
`BinaryEditorWindow._replace_instance_value()` for the current implementation.

### InfoSize

Static offsets and sizes are stored as `InfoSize` objects. The GUI displays and
accepts them in `byte,bit` format. For example, four bytes are written as `4,0`
and three bits as `0,3`. Offsets and sizes may also contain expression strings,
so do not unconditionally coerce every value to `InfoSize`.

### TreeviewEx

Use numeric column IDs such as `#1` and `#2`, rather than column names, when
configuring editable, read-only, or combobox cells. When adding or reordering
columns, update the corresponding column ID constants and tests.

### Saving Files

`Save` overwrites the currently open file or the file most recently selected
with `Save As`. For new data without a destination, it falls back to `Save As`.
`BinaryEditorWindow.binary_file` and `struct_layout_file` track the current
paths.

## Verifying Changes

Run the tests for the affected area first, followed by the complete test suite.
When changing GUI state transitions, verify at least these workflows:

- Open a StructLayout, then open a binary file.
- Open a binary file in raw mode, then open a StructLayout.
- Update Struct or Enum definitions, then use `Re-decode`.
- Edit a value, then save the binary file.
- Use `Save` to overwrite an open file.

## Build and Release

The project uses Hatchling to build distributions:

```powershell
uv build
```

PowerShell scripts are available for version updates:

```powershell
./bump_patch.ps1
./bump_minor.ps1
./bump_major.ps1
```

The workflows in `.github/workflows/` publish manually to TestPyPI or PyPI. The
PyPI workflow creates a tag and GitHub Release from the version in
`pyproject.toml`, then attaches the wheel and source distribution. Before
publishing, verify the version, run the complete test suite, and inspect the
artifacts produced by `uv build`.
