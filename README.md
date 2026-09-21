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

Generate a branch coverage report in the terminal:

```powershell
uv run pytest --cov=sltgui --cov-branch --cov-report=term-missing -q
```

Generate a browsable HTML coverage report in `htmlcov/`:

```powershell
uv run pytest --cov=sltgui --cov-branch --cov-report=html -q
```

Open `htmlcov/index.html` in a browser to inspect uncovered lines and branches.

## Source Layout

| Path | Responsibility |
| --- | --- |
| `src/sltgui/binary_editor_window.py` | Main window for opening, decoding, editing, encoding, and saving binary data |
| `src/sltgui/struct_def_dict_editor.py` | Modal editor for the `StructDef` dictionary |
| `src/sltgui/enum_def_dict_editor.py` | Modal editor for the `EnumDef` dictionary |
| `src/sltgui/payload_struct_def_editor.py` | Editor for ordered payload condition and StructLayout pairs |
| `src/sltgui/resources/` | StructLayout definitions bundled with the package |
| `src/sltgui/__init__.py` | Public API with lazy imports for the GUI classes |
| `tests/` | Unit tests with GUI dependencies replaced by stubs |

The package exposes five public classes:

```python
from sltgui import (BinaryEditorWindow, EnumDefDictEditor,
                    PacketDataEditorWindow, PayloadStructDefEditor,
                    StructDefDictEditor)
```

## Built-in PCAP and PCAPNG Layouts

The application includes ready-to-use StructLayouts for PCAP and PCAPNG files.
Load one from **Type Definition > Load Resource > PCAP** or **PCAPNG**. If
binary data is already open, it is decoded immediately with the selected
layout. The decoded tree can be expanded and collapsed at every nesting level.

Bundled layouts are loaded as editable copies and are not tied to the installed
package files. Use **Type Definition > Struct Definitions** or **Enum
Definitions** to edit them. **Save StructLayout** prompts for a destination the
first time, after which the saved copy can be updated normally.

The bundled PCAP and PCAPNG StructLayouts can be loaded without external JSON
files:

```python
from sltgui.resources import load_pcap_layout, load_pcapng_layout

pcap_layout = load_pcap_layout()
pcapng_layout = load_pcapng_layout()
```

The PCAPNG layout follows each block's total length, supports byte-order changes
between sections, and provides structured bodies for SHB, IDB, EPB, SPB, ISB,
DSB, and Custom Blocks. Options and unknown block bodies remain available as
raw bytes.

For PCAP records and PCAPNG Enhanced Packet Blocks on `LINKTYPE_ETHERNET`
interfaces, `packet_data` is expanded into Ethernet II, optional 802.1Q VLAN,
ARP, IPv4 or IPv6, and then TCP, UDP, ICMP or ICMPv6 fields. Unsupported link
types, EtherTypes, IP protocols, IPv6 extension headers, and application data
remain available as raw bytes. PCAPNG files with multiple interfaces currently
use the most recently decoded Interface Description Block's link type.

The bundled layouts define enums for link types, EtherTypes, IP protocol/next
header numbers, and ARP operations. Enum fields are displayed as `UDP (17)`.
Their Value cells accept either the enum name, such as `TCP`, or the combined
display form, such as `TCP (6)`. Unknown values remain numeric.

## Reassembled Packet Data Editor

Run `python -m sltgui.packet_data_editor_window` to inspect logical IP payloads
rather than individual capture frames. The independent editor uses the bundled
PCAP and PCAPNG layouts to validate the capture, supports Ethernet and VLAN
frames, and reassembles complete IPv4 and IPv6 fragment groups even when
fragments arrive out of order. The upper TreeviewEx is a read-only packet and
fragment summary.

Open **Packet Definition > Payload Struct Definitions** to register ordered
sltcalc condition and StructLayout pairs. The first matching pair decodes the
selected packet in the lower TreeviewEx, where field values can be edited in
place. If no StructLayout matches, the lower pane displays editable raw Hex
rows. Use **Bytes/row** to group each row into 1, 2, 4, 8, or 16 bytes. Each
edited row must retain its displayed byte count. Incomplete fragment groups
remain read-only.

### Payload Condition Environment

PayloadStructDefEditor evaluates each **Condition** as an sltcalc expression.
The expression can use the following packet values:

| Name | Type | Description |
| --- | --- | --- |
| `key` | `tuple` | Internal fragment-reassembly key. Fragmented packets use `(ip_version, source, destination, protocol, identification)`; unfragmented packets use `(ip_version, sequence)` |
| `payload` | byte sequence | Complete or partial reassembled IP payload. Indexing returns an integer byte value |
| `ip_version` | `int` | IP version, either `4` or `6` |
| `source` | `bytes` | Raw source IPv4 or IPv6 address bytes |
| `destination` | `bytes` | Raw destination IPv4 or IPv6 address bytes |
| `protocol` | `int` | IPv4 Protocol or final IPv6 Next Header number, such as `6` for TCP or `17` for UDP |
| `identification` | `int` or `None` | IPv4 Identification or IPv6 Fragment Identification. It is `None` for an unfragmented IPv6 packet |

The enum definitions bundled with `pcap.json` and `pcapng.json` are also
available by name. Enum members use attribute syntax, such as
`EtherType.IPV4` and `IpProtocol.UDP`.

Conditions can also use the mathematical expression syntax provided by the
StructLayoutToolkit sltcore/sltcalc stack. This includes arithmetic,
comparison, logical, indexing, and bitwise expressions. The safe functions
`abs`, `all`, `any`, `len`, `max`, `min`, `round`, `sorted`, and `sum` are also
available.

For example:

```python
protocol == 17 and len(payload) >= 8
len(payload) * 8 >= 64
ip_version == 4 and source == b"\xc0\x00\x02\x01"
protocol == 17 and payload[0] == 0x30
identification is not None and identification == 0x1234
```

Definitions are evaluated from top to bottom, and the first truthy Condition
selects its StructLayout. Use `True` as a final catch-all Condition. Definitions
can be reordered in PayloadStructDefEditor. Its **Type Definition** menu selects
the root StructDef and opens StructDefDictEditor or EnumDefDictEditor for the
selected layout.
Edits encode the StructInstance, update TCP, UDP, ICMP, or ICMPv6 checksums,
and write through to the original fragments. Encoded data must retain its
original length so capture record and fragment boundaries remain unchanged.

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

### Lua Plugins

Place `*.lua` plugin files in `apl_dir/plugins`. `apl_dir` is the directory
passed to `BinaryEditorWindow`; when omitted, it is the application's current
working directory. No plugin directory means no hooks run, preserving the
normal decode and encode behavior.

Each plugin returns a table with optional `decode(instance)` and
`encode(instance)` hooks. `decode` runs after `sltcodec.decode()` and should
convert encoded values into display values. `encode` runs immediately before
`sltcodec.encode()` and must perform the inverse conversion. A hook receives a
`StructInstance` and returns the instance to use; returning `nil` keeps the
same instance. Plugins run in filename order.

The bundled example [plugins/pcap_timestamp_plugin.lua](plugins/pcap_timestamp_plugin.lua)
formats PCAP and PCAPNG timestamps as UTC strings with nine fractional digits.
It stores the formatted text in the timestamp `StructInstance.display_value`,
so BinaryEditorWindow displays and edits the value on the parent row while its
child fields retain their raw numeric values. The encode hook parses the edited
parent value and updates the immutable child fields with `with_value()` before
serialization.

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
