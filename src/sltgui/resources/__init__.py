"""Bundled StructLayout resources."""
from importlib.resources import as_file, files

from sltcodec import StructLayout, load_struct_layout
from sltmodel.resources import load_pcap_layout, load_pcapng_layout

__all__ = [
    "load_elf_layout", "load_pcap_layout", "load_pcapng_layout",
    "load_pe_layout"
]


def _load_layout(filename: str) -> StructLayout:
    resource = files(__name__).joinpath(filename)
    with as_file(resource) as path:
        return load_struct_layout(path)


def load_pe_layout() -> StructLayout:
    """Load the bundled PE StructLayout."""
    return _load_layout("pe.json")


def load_elf_layout() -> StructLayout:
    """Load the bundled ELF StructLayout."""
    return _load_layout("elf.json")
