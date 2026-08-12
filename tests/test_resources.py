"""Tests for bundled StructLayout resources."""
from importlib.resources import as_file, files

from sltcodec import decode, load_struct_layout

from sltgui.resources import load_pcap_layout, load_pcapng_layout


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
