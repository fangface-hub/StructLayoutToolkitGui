"""Tests for Lua StructInstance transformation plugins."""
from pathlib import Path
from types import SimpleNamespace

from sltgui.lua_plugins import LuaPluginManager

_FieldInstance = type(
    "FieldInstance",
    (),
    {
        "__init__":
        lambda self, name, value: self.__dict__.update(
            field_def=SimpleNamespace(name=name), value=value),
        "with_value":
        lambda self, value: type(self)(self.field_def.name, value),
    },
)


def test_lua_plugins_are_noop_when_directory_is_missing(tmp_path):
    """A missing plugins directory preserves the original instance."""
    instance = object()

    manager = LuaPluginManager(tmp_path / "plugins")

    assert manager.apply_decode(instance) is instance
    assert manager.apply_encode(instance) is instance


def test_lua_plugins_apply_decode_then_encode_hooks(tmp_path):
    """Lua hooks can transform a StructInstance-like Python object."""
    (tmp_path / "epoch.lua").write_text(
        """return {
  decode = function(instance)
  local function increment(instance)
  for index = 0, #instance.field_instances - 1 do
    local field = instance.field_instances[index]
    if field.is_struct then
      increment(field.value)
    else
      instance.field_instances[index] = field:with_value(field.value + 1)
    end
  end
  end
  increment(instance)
    return instance
  end,
  encode = function(instance)
  local function decrement(instance)
  for index = 0, #instance.field_instances - 1 do
    local field = instance.field_instances[index]
    if field.is_struct then
      decrement(field.value)
    else
      field.value = field.value - 1
    end
  end
  end
  decrement(instance)
    return instance
  end,
}
""",
        encoding="utf-8",
    )

    instance_type = type(
        "ItemAccessibleStructInstance",
        (),
        {
            "__getitem__": lambda self, index: self.field_instances[index]
        },
    )
    timestamp_instance = instance_type()
    timestamp_instance.field_instances = [
        _FieldInstance("timestamp_seconds", 1700000000),
        _FieldInstance("timestamp_nanoseconds", 1700000001),
    ]
    nested_instance = instance_type()
    nested_instance.field_instances = [
        _FieldInstance("pcap_timestamp", timestamp_instance),
    ]
    instance = instance_type()
    instance.field_instances = [_FieldInstance("record", nested_instance)]
    manager = LuaPluginManager(tmp_path)

    displayed_instance = manager.apply_decode(instance)
    displayed_record = displayed_instance.field_instances[0].value
    displayed_timestamp = displayed_record.field_instances[0].value
    assert displayed_timestamp.field_instances[0].value == 1700000001
    assert displayed_timestamp.field_instances[1].value == 1700000002

    encoded_instance = manager.apply_encode(displayed_instance)

    displayed_record = displayed_instance.field_instances[0].value
    displayed_timestamp = displayed_record.field_instances[0].value
    assert displayed_timestamp.field_instances[0].value == 1700000001
    assert displayed_timestamp.field_instances[1].value == 1700000002

    encoded_record = encoded_instance.field_instances[0].value
    encoded_timestamp = encoded_record.field_instances[0].value
    assert encoded_timestamp.field_instances[0].value == 1700000000
    assert encoded_timestamp.field_instances[1].value == 1700000001


def test_pcap_timestamp_plugin_formats_pcap_and_pcapng_timestamps():
    """The PCAP timestamp plugin presents capture timestamps consistently."""
    instance_type = type("StructInstance", (), {})

    def nested(*fields):
        instance = instance_type()
        instance.field_instances = list(fields)
        return instance

    seconds = 1700000000
    pcap_timestamp = nested(
        _FieldInstance("timestamp_seconds", seconds),
        _FieldInstance("timestamp_nanoseconds", 123456789),
    )
    pcapng_value = seconds * 1000000 + 123456
    pcapng_timestamp = nested(
        _FieldInstance("high", pcapng_value >> 32),
        _FieldInstance("low", pcapng_value & 0xFFFFFFFF),
    )
    pcapng_nanosecond_value = seconds * 1000000000 + 987654321
    pcapng_nanosecond_timestamp = nested(
        _FieldInstance("high", pcapng_nanosecond_value >> 32),
        _FieldInstance("low", pcapng_nanosecond_value & 0xFFFFFFFF),
    )
    instance = nested(
        _FieldInstance("pcap_timestamp", pcap_timestamp),
        _FieldInstance("timestamp", pcapng_timestamp),
        _FieldInstance("timestamp", pcapng_nanosecond_timestamp),
    )
    plugins_dir = Path(__file__).parents[1] / "plugins"
    manager = LuaPluginManager(plugins_dir)

    displayed = manager.apply_decode(instance)

    displayed_pcap = displayed.field_instances[0].value
    displayed_pcapng = displayed.field_instances[1].value
    displayed_pcapng_nanosecond = displayed.field_instances[2].value
    assert displayed_pcap.display_value == "2023-11-14 22:13:20.123456789"
    assert displayed_pcapng.display_value == "2023-11-14 22:13:20.123456000"
    assert displayed_pcapng_nanosecond.display_value == (
        "2023-11-14 22:13:20.987654321")
    assert [field.value for field in displayed_pcap.field_instances] == [
        seconds,
        123456789,
    ]
    assert [field.value for field in displayed_pcapng.field_instances] == [
        pcapng_value >> 32,
        pcapng_value & 0xFFFFFFFF,
    ]

    displayed_pcap.display_value = "2023-11-14 22:13:21.123456789"

    encoded = manager.apply_encode(displayed)

    pcap_fields = encoded.field_instances[0].value.field_instances
    pcapng_fields = encoded.field_instances[1].value.field_instances
    pcapng_nanosecond_fields = encoded.field_instances[2].value.field_instances
    assert [field.value for field in pcap_fields] == [seconds + 1, 123456789]
    encoded_high = pcapng_fields[0].value
    encoded_low = pcapng_fields[1].value
    encoded_pcapng_value = encoded_high << 32 | encoded_low
    assert encoded_pcapng_value == pcapng_value
    encoded_high = pcapng_nanosecond_fields[0].value
    encoded_low = pcapng_nanosecond_fields[1].value
    encoded_pcapng_value = encoded_high << 32 | encoded_low
    assert encoded_pcapng_value == pcapng_nanosecond_value
