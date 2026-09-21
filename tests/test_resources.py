"""Tests for bundled StructLayout resources."""
from importlib.resources import as_file, files

from sltcalc import SAFE_FUNCS
from sltcodec import decode, load_struct_layout
from sltcore import InfoSize

from sltgui.resources import (load_elf_layout, load_pcap_layout,
                              load_pcapng_layout, load_pe_layout)


def _field_value(instance, name):
    return next(field.value for field in instance.field_instances
                if field.field_def.name == name)


def test_load_pcap_layout():
    """The bundled PCAP layout is loadable and selects its root struct."""
    layout = load_pcap_layout()

    assert layout.struct_def_name == "pcap_file"
    assert {
        "pacp_file_header",
        "packet_record",
        "pcap_timestamp",
        "pcap_file",
    }.issubset(layout.type_dict.struct_dict)
    assert "ethernet_frame" in layout.type_dict.struct_dict
    assert {"LinkType", "EtherType", "IpProtocol",
            "ArpOperation"} <= set(layout.type_dict.enum_dict)
    assert layout.type_dict.enum_dict["IpProtocol"].values["UDP"] == 17
    assert next(field
                for field in layout.type_dict.struct_dict["ipv4_packet"].fields
                if field.name == "protocol").enum_def_name == "IpProtocol"


def test_directly_loaded_pcap_contains_packet_structures():
    """The PCAP JSON contains its referenced packet types."""
    resource = files("sltgui.resources").joinpath("pcap.json")
    with as_file(resource) as path:
        layout = load_struct_layout(path)

    assert "ethernet_frame" in layout.type_dict.struct_dict


def test_decode_little_endian_pcap_packet_data():
    """PCAP Ethernet packet data is decoded through the transport layer."""
    data = bytes.fromhex(
        "d4c3b2a1 0200 0400 00000000 00000000 ffff0000 01000000 "
        "01000000 02000000 2e000000 2e000000 "
        "001122334455 66778899aabb 0800 "
        "4500 0020 1234 0000 4011 0000 c0000201 c6336402 "
        "3039 0035 000c 0000 deadbeef")

    resource = files("sltgui.resources").joinpath("pcap.json")
    with as_file(resource) as path:
        layout = load_struct_layout(path)
    instance = decode(layout, data)
    header = _field_value(instance, "header")
    record = next(field.value for field in instance.field_instances
                  if field.field_def.name.startswith("record["))
    timestamp = _field_value(record, "pcap_timestamp")
    packet_data = next(field for field in record.field_instances
                       if field.field_def.name == "packet_data")
    ethernet = packet_data.value
    ipv4 = _field_value(ethernet, "network_packet")
    udp = _field_value(ipv4, "transport_segment")

    assert _field_value(header, "link_type") == 1
    assert timestamp.size.byte == 8
    assert _field_value(timestamp, "timestamp_seconds") == 1
    assert _field_value(timestamp, "timestamp_nanoseconds") == 2
    assert _field_value(record, "captured_packet_length") == 46
    assert packet_data.field_def.type.name == "ethernet_frame"
    assert ethernet.struct_def.name == "ethernet_frame"
    assert _field_value(ethernet, "ether_type") == 0x0800
    assert ipv4.struct_def.name == "ipv4_packet"
    assert _field_value(ipv4, "source_address") == bytearray.fromhex("c0000201")
    assert udp.struct_def.name == "udp_datagram"
    assert _field_value(udp, "destination_port") == 53
    assert _field_value(udp,
                        "application_data") == bytearray.fromhex("deadbeef")


def test_load_pcapng_layout():
    """The bundled PCAPNG layout is loadable and selects its root struct."""
    layout = load_pcapng_layout()

    assert layout.struct_def_name == "pcapng_file"
    assert "pcapng_block" in layout.type_dict.struct_dict
    assert "enhanced_packet_block_body" in layout.type_dict.struct_dict
    assert {"LinkType", "EtherType", "IpProtocol",
            "ArpOperation"} <= set(layout.type_dict.enum_dict)
    assert next(field
                for field in layout.type_dict.struct_dict["ipv6_packet"].fields
                if field.name == "next_header").enum_def_name == "IpProtocol"


def test_load_pe_layout():
    """The bundled PE layout exposes executable header structures and enums."""
    layout = load_pe_layout()

    assert layout.struct_def_name == "pe_file"
    assert {
        "pe_dos_header", "pe_coff_header", "pe_section_header",
        "pe_optional_header_32", "pe_optional_header_64"
    } <= set(layout.type_dict.struct_dict)
    assert {
        "Machine", "OptionalHeaderMagic", "Subsystem", "SectionCharacteristics"
    } <= set(layout.type_dict.enum_dict)


def test_load_elf_layout():
    """The bundled ELF layout exposes 32/64-bit structures and enums."""
    layout = load_elf_layout()

    assert layout.struct_def_name == "elf_file"
    assert {
        "elf_program_header_32",
        "elf_program_header_64",
        "elf_section_header_32",
        "elf_section_header_64",
    } <= set(layout.type_dict.struct_dict)
    assert {
        "Class", "DataEncoding", "Machine", "ProgramType", "SectionType",
        "SectionFlags"
    } <= set(layout.type_dict.enum_dict)


def test_decode_minimal_elf64_headers():
    """The ELF layout follows ELF64 offsets and decodes dynamic tables."""
    SAFE_FUNCS["InfoSize"] = InfoSize
    data = bytearray(184)
    data[0:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    data[6] = 1
    data[16:18] = (3).to_bytes(2, "little")
    data[18:20] = (62).to_bytes(2, "little")
    data[20:24] = (1).to_bytes(4, "little")
    data[24:32] = (0x400000).to_bytes(8, "little")
    data[32:40] = (64).to_bytes(8, "little")
    data[40:48] = (120).to_bytes(8, "little")
    data[52:54] = (64).to_bytes(2, "little")
    data[54:56] = (56).to_bytes(2, "little")
    data[56:58] = (1).to_bytes(2, "little")
    data[58:60] = (64).to_bytes(2, "little")
    data[60:62] = (1).to_bytes(2, "little")
    data[64:68] = (1).to_bytes(4, "little")
    data[68:72] = (5).to_bytes(4, "little")
    data[72:80] = (0x1000).to_bytes(8, "little")
    data[120 + 4:120 + 8] = (1).to_bytes(4, "little")
    data[120 + 8:120 + 16] = (6).to_bytes(8, "little")

    instance = decode(load_elf_layout(), data)
    program_header = next(field.value for field in instance.field_instances
                          if field.field_def.name.startswith("program_headers"))

    assert _field_value(instance, "elf_class") == 2
    assert _field_value(instance, "e_machine") == 62
    assert _field_value(program_header, "p_type") == 1
    assert not any(field.field_def.name == "section_headers"
                   for field in instance.field_instances)


def test_decode_minimal_pe32_headers():
    """The PE layout follows e_lfanew and decodes a PE32 section header."""
    SAFE_FUNCS["InfoSize"] = InfoSize
    data = bytearray(0x178 + 40)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x14C).to_bytes(2, "little")
    data[0x86:0x88] = (1).to_bytes(2, "little")
    data[0x94:0x96] = (0xE0).to_bytes(2, "little")
    data[0x96:0x98] = (2).to_bytes(2, "little")
    data[0x98:0x9A] = (0x10B).to_bytes(2, "little")
    data[0xD4:0xD8] = (0).to_bytes(4, "little")
    data[0x178:0x180] = b".text\0\0\0"
    data[0x180:0x184] = (0x1000).to_bytes(4, "little")
    data[0x184:0x188] = (0x1000).to_bytes(4, "little")
    data[0x188:0x18C] = (0x200).to_bytes(4, "little")
    data[0x18C:0x190] = (0x400).to_bytes(4, "little")

    instance = decode(load_pe_layout(), data)
    dos_header = _field_value(instance, "dos_header")
    coff_header = _field_value(instance, "coff_header")
    section = _field_value(instance, "section_headers")

    assert _field_value(dos_header, "e_magic") == 0x5A4D
    assert _field_value(coff_header, "Machine") == 0x14C
    assert _field_value(section, "Name") == bytearray(b".text\0\0\0")


def test_decode_little_endian_pcapng_blocks():
    """The layout follows block lengths and decodes common block bodies."""
    data = bytes.fromhex("0a0d0d0a 1c000000 4d3c2b1a 0100 0000 "
                         "ffffffffffffffff 1c000000 "
                         "01000000 14000000 0100 0000 ffff0000 14000000 "
                         "06000000 50000000 00000000 01000000 02000000 "
                         "2e000000 2e000000 "
                         "001122334455 66778899aabb 0800 "
                         "4500 0020 1234 0000 4011 0000 c0000201 c6336402 "
                         "3039 0035 000c 0000 deadbeef 0000 50000000")

    instance = decode(load_pcapng_layout(), data)
    blocks = [
        field.value for field in instance.field_instances
        if field.field_def.name.startswith("block[")
    ]

    assert len(blocks) == 3
    assert [_field_value(block, "block_total_length")
            for block in blocks] == [28, 20, 80]
    assert [_field_value(block, "body").struct_def.name
            for block in blocks] == [
                "section_header_block_body",
                "interface_description_block_body",
                "enhanced_packet_block_body",
            ]
    assert _field_value(_field_value(blocks[1], "body"), "link_type") == 1
    enhanced_packet = _field_value(blocks[2], "body")
    timestamp = _field_value(enhanced_packet, "timestamp")
    assert timestamp.size.byte == 8
    assert _field_value(timestamp, "high") == 1
    assert _field_value(timestamp, "low") == 2
    ethernet = _field_value(enhanced_packet, "packet_data")
    ipv4 = _field_value(ethernet, "network_packet")
    udp = _field_value(ipv4, "transport_segment")

    assert ethernet.struct_def.name == "ethernet_frame"
    assert _field_value(ethernet,
                        "destination_mac") == bytearray.fromhex("001122334455")
    assert _field_value(ethernet, "ether_type") == 0x0800
    assert ipv4.struct_def.name == "ipv4_packet"
    assert _field_value(ipv4, "protocol") == 17
    assert _field_value(ipv4, "source_address") == bytearray.fromhex("c0000201")
    assert udp.struct_def.name == "udp_datagram"
    assert _field_value(udp, "source_port") == 12345
    assert _field_value(udp, "destination_port") == 53
    assert _field_value(udp,
                        "application_data") == bytearray.fromhex("deadbeef")


def test_decode_pcapng_section_endianness_change():
    """A later Section Header Block can change byte order."""
    data = bytes.fromhex("0a0d0d0a 1c000000 4d3c2b1a 0100 0000 "
                         "ffffffffffffffff 1c000000 "
                         "0a0d0d0a 0000001c 1a2b3c4d 0001 0000 "
                         "ffffffffffffffff 0000001c "
                         "00000001 00000014 0001 0000 0000ffff 00000014")

    instance = decode(load_pcapng_layout(), data)
    blocks = [
        field.value for field in instance.field_instances
        if field.field_def.name.startswith("block[")
    ]

    assert [_field_value(block, "block_total_length")
            for block in blocks] == [28, 28, 20]
    assert _field_value(_field_value(blocks[2], "body"), "link_type") == 1
    assert _field_value(_field_value(blocks[2], "body"), "snap_len") == 65535
