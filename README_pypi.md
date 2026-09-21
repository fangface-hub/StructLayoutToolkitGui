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
- Load bundled PCAP and PCAPNG StructLayouts from the application menu.
- Expand and collapse deeply nested decoded structures.
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

## Built-in PCAP and PCAPNG Support

Use **Type Definition > Load Resource > PCAP** or **PCAPNG** to load a bundled
StructLayout without locating a separate JSON file. If a binary file is already
open, it is decoded immediately. Expand the tree nodes to inspect nested packet
headers and payloads.

For Ethernet captures, `packet_data` is decoded into Ethernet II, optional
802.1Q VLAN, ARP, IPv4 or IPv6, and then TCP, UDP, ICMP or ICMPv6 fields.
Unsupported link types, EtherTypes, IP protocols, IPv6 extension headers, and
application data remain visible as raw bytes.

The bundled layout is loaded as an editable copy. It can be changed with
**Type Definition > Struct Definitions** or **Enum Definitions**. Choose
**Save StructLayout** to select a destination and save the customized layout.

PCAPNG parsing follows block lengths, supports byte-order changes between
sections, and provides structured bodies for Section Header, Interface
Description, Enhanced Packet, Simple Packet, Interface Statistics, Decryption
Secrets, and Custom Blocks. Options and unknown block bodies are retained as
raw bytes. Files with multiple interfaces currently use the most recently
decoded Interface Description Block's link type.

The bundled layouts define enums for link types, EtherTypes, IP protocol/next
header numbers, and ARP operations. Enum fields are shown as `UDP (17)` and
accept enum names such as `TCP` when edited. Unknown values remain numeric.

The Binary Editor also includes a bundled Portable Executable (PE) layout.
Choose **Type Definition > Load Resource > PE** to inspect Windows executable
files. It supports the DOS header, PE signature, COFF header, PE32 and PE32+
optional headers, data directories, and section headers. The layout defines
enums for machine types, optional-header formats, subsystems, COFF flags, DLL
characteristics, and section characteristics.

The same resources are available from Python:

```python
from sltgui.resources import load_pcap_layout, load_pcapng_layout, load_pe_layout

pcap_layout = load_pcap_layout()
pcapng_layout = load_pcapng_layout()
pe_layout = load_pe_layout()
```

## Reassembled Packet Data Editor

Run `python -m sltgui.packet_data_editor_window` to reassemble IPv4 or IPv6
fragments from a PCAP or PCAPNG capture. The upper TreeviewEx is a read-only
packet and fragment summary. Use **Packet Definition > Payload Struct
Definitions** to register ordered sltcalc condition and StructLayout pairs.
The first matching layout decodes the selected packet in the lower TreeviewEx,
where field values can be edited. When no StructLayout matches, the lower pane
provides editable raw Hex rows. **Bytes/row** groups them into 1, 2, 4, 8, or
16 bytes, and an edited row must retain its displayed byte count.

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
selects its StructLayout. Use `True` as a final catch-all Condition.

The payload definition editor also opens the root StructDef selector and the
Struct and Enum definition editors for its selected layout. Edits update
transport checksums and write through to the original fragments. The encoded
length must remain unchanged; incomplete fragment groups are read-only.

## Lua Plugins

Place `*.lua` files in `apl_dir/plugins`, where `apl_dir` is the directory
passed to `BinaryEditorWindow` (or the current working directory by default).
Plugins may return `decode(instance)` and `encode(instance)` hooks to convert a
`StructInstance` between encoded and display values. Decode hooks run after
decoding; encode hooks run immediately before encoding. Without a plugins
directory, the application behaves exactly as it did previously. The bundled
`plugins/pcap_timestamp_plugin.lua` formats PCAP and PCAPNG timestamps while
keeping their child fields as raw numeric values. See the development README
for the hook contract.

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
