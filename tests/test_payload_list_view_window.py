"""Tests for the read-only payload list view."""
import types

import pytest

import sltgui.payload_list_view_window as payload_view_module
from sltgui.payload_list_view_window import (PayloadListViewWindow,
                                             _collect_fields,
                                             collect_payload_rows)


def _field(name, value):
    return types.SimpleNamespace(
        field_def=types.SimpleNamespace(name=name),
        value=value,
    )


def _packet(sequence, data, *, complete=True, protocol=17,
            identification=0x1234, timestamp="time"):
    return types.SimpleNamespace(
        sequence=sequence,
        complete=complete,
        data=data,
        identification=identification,
        timestamps={"timestamp": timestamp},
        ip_version=4,
        source="192.0.2.1",
        destination="198.51.100.2",
        protocol=protocol,
    )


def _editor(packets):
    return types.SimpleNamespace(
        document=types.SimpleNamespace(packets=packets),
        PROTOCOL_NAMES={17: "UDP"},
        _plugin_manager=lambda: types.SimpleNamespace(
            apply_decode=lambda instance: instance),
    )


def test_collect_fields_flattens_nested_instance_fields(monkeypatch):
    """Nested fields are flattened into stable dotted column names."""
    nested = types.SimpleNamespace(field_instances=[
        _field("inner", 42),
    ])
    instance = types.SimpleNamespace(field_instances=[
        _field("first", "one"),
        _field("group", nested),
    ])
    layout = types.SimpleNamespace(type_dict="type-dict")
    formatted = []
    monkeypatch.setattr(
        payload_view_module,
        "format_field_value",
        lambda field_instance, type_dict:
        formatted.append((field_instance, type_dict)) or
        f"value:{field_instance.value}",
    )
    fields = {}

    _collect_fields(instance, layout, "", fields)

    assert fields == {"first": "value:one", "group.inner": "value:42"}
    assert [type_dict for _, type_dict in formatted] == [
        "type-dict", "type-dict",
    ]


def test_collect_payload_rows_filters_packets_and_unions_fields(monkeypatch):
    """Matching complete packets decode and union field names in encounter order."""
    packets = [
        _packet(0, b"incomplete", complete=False),
        _packet(1, b"unmatched", protocol=99),
        _packet(2, b"first", identification=None, timestamp="first"),
        _packet(3, b"second", protocol=99, timestamp="second"),
    ]
    editor = _editor(packets)
    layout = types.SimpleNamespace(
        struct_def_name="UDP",
        type_dict="type-dict",
    )
    definition = types.SimpleNamespace(struct_layout=layout)
    matches = []
    monkeypatch.setattr(
        payload_view_module,
        "matching_struct_layout",
        lambda definitions, packet:
        matches.append((definitions, packet)) or
        (layout if packet.sequence in (2, 3) else None),
    )
    decoded_data = []
    instances = {
        b"first": types.SimpleNamespace(field_instances=[
            _field("alpha", 1),
            _field("nested", types.SimpleNamespace(field_instances=[
                _field("child", 2),
            ])),
        ]),
        b"second": types.SimpleNamespace(field_instances=[
            _field("nested", types.SimpleNamespace(field_instances=[
                _field("child", 3),
            ])),
            _field("beta", 4),
        ]),
    }
    monkeypatch.setattr(
        payload_view_module,
        "decode",
        lambda selected_layout, data:
        decoded_data.append((selected_layout, data)) or instances[data],
    )
    monkeypatch.setattr(
        payload_view_module,
        "format_field_value",
        lambda field_instance, _type_dict: str(field_instance.value),
    )
    progress = []
    dialogs = []

    def run_with_progress(parent, title, worker):
        dialogs.append((parent, title))
        return worker(progress.append)

    monkeypatch.setattr(payload_view_module, "run_with_progress",
                        run_with_progress)
    parent = object()

    names, rows = collect_payload_rows(editor, parent, definition)

    assert dialogs == [(parent, "Decoding packets (UDP)...")]
    assert progress == [0, 0.25, 0.5, 0.75, 1.0]
    assert decoded_data == [(layout, b"first"), (layout, b"second")]
    assert [packet.sequence for _, packet in matches] == [1, 2, 3]
    assert all(definitions == [definition] for definitions, _ in matches)
    assert names == ["alpha", "nested.child", "beta"]
    assert rows == [
        (3, "first", 4, "192.0.2.1", "198.51.100.2", "UDP", "", 5,
         "Complete", "1", "2", ""),
        (4, "second", 4, "192.0.2.1", "198.51.100.2", "99", "0x00001234",
         6, "Complete", "", "3", "4"),
    ]


def test_collect_payload_rows_handles_empty_capture(monkeypatch):
    """An empty capture reports completion without dividing by zero."""
    editor = _editor([])
    definition = types.SimpleNamespace(
        struct_layout=types.SimpleNamespace(struct_def_name="Empty"))
    progress = []
    monkeypatch.setattr(
        payload_view_module,
        "run_with_progress",
        lambda _parent, _title, worker: worker(progress.append),
    )

    assert collect_payload_rows(editor, object(), definition) == ([], [])
    assert progress == [1.0]


def test_view_window_initializes_and_populates_definitions(monkeypatch):
    """Initialization wires its editor and loads available definitions."""
    calls = []
    monkeypatch.setattr(payload_view_module.tk.Toplevel, "__init__",
                        lambda self, parent: calls.append(("parent", parent)))
    monkeypatch.setattr(PayloadListViewWindow, "title",
                        lambda self, title: calls.append(("title", title)))
    monkeypatch.setattr(PayloadListViewWindow, "geometry",
                        lambda self, geometry: calls.append(("geometry",
                                                             geometry)))
    monkeypatch.setattr(PayloadListViewWindow, "_build_ui",
                        lambda self: calls.append(("ui", self)))
    monkeypatch.setattr(PayloadListViewWindow, "_refresh_definitions",
                        lambda self: calls.append(("refresh", self)))
    editor = object()
    parent = object()
    view = object.__new__(PayloadListViewWindow)

    view.__init__(parent, editor)

    assert view.editor is editor
    assert calls == [
        ("parent", parent),
        ("title", "Payload List View"),
        ("geometry", "1080x620"),
        ("ui", view),
        ("refresh", view),
    ]


def test_build_ui_creates_condition_selector_and_readonly_tree(monkeypatch):
    """The view lays out a selector, table, and status label."""
    widget_calls = []

    class Widget:
        def __init__(self, parent=None, **options):
            self.parent = parent
            self.options = options
            self.calls = []
            widget_calls.append(self)

        def pack(self, *args, **kwargs):
            self.calls.append(("pack", args, kwargs))

        def bind(self, *args, **kwargs):
            self.calls.append(("bind", args, kwargs))

        def configure(self, *args, **kwargs):
            self.calls.append(("configure", args, kwargs))

        def heading(self, *args, **kwargs):
            self.calls.append(("heading", args, kwargs))

        def column(self, *args, **kwargs):
            self.calls.append(("column", args, kwargs))

        def set_readonly_column(self, *args, **kwargs):
            self.calls.append(("readonly", args, kwargs))

    class Style:
        def __init__(self, _parent):
            pass

        def configure(self, *args, **kwargs):
            widget_calls.append(("style", args, kwargs))

    monkeypatch.setattr(payload_view_module.ttk, "Style", Style)
    monkeypatch.setattr(payload_view_module.ttk, "Frame", Widget)
    monkeypatch.setattr(payload_view_module.ttk, "Label", Widget)
    monkeypatch.setattr(payload_view_module.ttk, "Combobox", Widget)
    monkeypatch.setattr(payload_view_module.ttk, "Labelframe", Widget)
    monkeypatch.setattr(payload_view_module, "TreeviewEx", Widget)
    view = object.__new__(PayloadListViewWindow)
    view._on_definition_selected = lambda event: None

    view._build_ui()

    assert view.definition_combo.options == {"state": "readonly"}
    assert view.tree.options["show"] == "headings"
    assert view.tree.options["selectmode"] == "browse"
    assert [call[1][0] for call in view.tree.calls
            if call[0] == "readonly"] == [
                f"#{index}"
                for index in range(1, len(view.PACKET_COLUMNS) + 1)
            ]
    assert view.status_label.options["text"] == "Select a payload condition."
    assert any(call[0] == "bind" and
               call[1][0] == "<<ComboboxSelected>>"
               for call in view.definition_combo.calls)


def test_configure_columns_includes_packet_and_dynamic_field_columns(
        monkeypatch):
    """Dynamic field headings follow all packet columns and are readonly."""
    view = object.__new__(PayloadListViewWindow)
    calls = []
    view.tree = types.SimpleNamespace(
        configure=lambda **kwargs: calls.append(("configure", kwargs)),
        heading=lambda *args, **kwargs: calls.append(("heading", args,
                                                       kwargs)),
        column=lambda *args, **kwargs: calls.append(("column", args,
                                                     kwargs)),
        set_readonly_column=lambda *args, **kwargs: calls.append((
            "readonly", args, kwargs)),
    )

    view._configure_columns(("source.port", "flags"))

    columns = tuple(name for name, _, _ in view.PACKET_COLUMNS) + ("f0", "f1")
    assert calls[0] == ("configure", {
        "columns": columns,
        "displaycolumns": columns,
    })
    assert ("heading", ("f0",), {"text": "source.port"}) in calls
    assert ("heading", ("f1",), {"text": "flags"}) in calls
    assert [call[1][0] for call in calls if call[0] == "readonly"] == [
        f"#{index}" for index in range(1, len(columns) + 1)
    ]


def test_refresh_definitions_handles_empty_and_selects_first(monkeypatch):
    """Definitions populate the combobox and select the first when present."""
    view = object.__new__(PayloadListViewWindow)
    definitions = [
        types.SimpleNamespace(
            condition="protocol == 17",
            struct_layout=types.SimpleNamespace(struct_def_name="UDP"),
        ),
    ]
    values = []
    current = []
    selected = []
    view.editor = types.SimpleNamespace(payload_struct_defs=[])
    view.definition_combo = types.SimpleNamespace(
        configure=lambda **kwargs: values.append(kwargs["values"]),
        current=current.append,
    )
    view._on_definition_selected = lambda: selected.append(True)

    view._refresh_definitions()
    view.editor.payload_struct_defs = definitions
    view._refresh_definitions()

    assert values == [[], ["protocol == 17  [UDP]"]]
    assert current == [0]
    assert selected == [True]


def test_definition_selection_handles_missing_capture_or_invalid_index():
    """Missing captures and invalid combobox indexes show an empty state."""
    view = object.__new__(PayloadListViewWindow)
    view.editor = types.SimpleNamespace(
        payload_struct_defs=[object()],
        document=None,
    )
    view.definition_combo = types.SimpleNamespace(current=lambda: 0)
    deleted = []
    statuses = []
    view.tree = types.SimpleNamespace(
        get_children=lambda: ("stale",),
        delete=lambda *rows: deleted.append(rows),
    )
    view.status_label = types.SimpleNamespace(
        configure=lambda **kwargs: statuses.append(kwargs["text"]))

    view._on_definition_selected()
    view.editor.document = object()
    view.definition_combo.current = lambda: -1
    view._on_definition_selected()

    assert deleted == [("stale",), ("stale",)]
    assert statuses == ["No capture or definition.",
                        "No capture or definition."]


@pytest.mark.parametrize("exception", [
    payload_view_module.OperationCanceledError(),
    ValueError("invalid definition"),
    AttributeError("missing field"),
])
def test_definition_selection_handles_decode_cancel_and_errors(
        monkeypatch, exception):
    """Canceled decode preserves the view; expected errors are reported."""
    definition = object()
    view = object.__new__(PayloadListViewWindow)
    view.editor = types.SimpleNamespace(
        payload_struct_defs=[definition],
        document=object(),
    )
    view.definition_combo = types.SimpleNamespace(current=lambda: 0)
    view.tree = types.SimpleNamespace(
        get_children=lambda: (),
        delete=lambda *_rows: None,
    )
    statuses = []
    view.status_label = types.SimpleNamespace(
        configure=lambda **kwargs: statuses.append(kwargs["text"]))
    calls = []
    view._configure_columns = lambda names: calls.append(("columns", names))
    view.tree.insert = lambda *args, **kwargs: calls.append(("insert", args,
                                                             kwargs))
    monkeypatch.setattr(
        payload_view_module,
        "collect_payload_rows",
        lambda *_args: (_ for _ in ()).throw(exception),
    )
    errors = []
    monkeypatch.setattr(
        payload_view_module.messagebox,
        "showerror",
        lambda *args, **kwargs: errors.append((args, kwargs)),
    )

    view._on_definition_selected()

    if isinstance(exception, payload_view_module.OperationCanceledError):
        assert errors == []
        assert statuses == []
    else:
        assert errors == [(("Decode Error", str(exception)), {"parent": view})]
        assert statuses == []
    assert calls == []


def test_definition_selection_configures_and_inserts_rows(monkeypatch):
    """Successful selection rebuilds columns, rows, and matching count."""
    definition = object()
    view = object.__new__(PayloadListViewWindow)
    view.editor = types.SimpleNamespace(
        payload_struct_defs=[definition],
        document=object(),
    )
    view.definition_combo = types.SimpleNamespace(current=lambda: 0)
    deleted = []
    inserted = []
    view.tree = types.SimpleNamespace(
        get_children=lambda: ("stale",),
        delete=lambda *rows: deleted.append(rows),
        insert=lambda *args, **kwargs: inserted.append((args, kwargs)),
    )
    configured = []
    statuses = []
    view._configure_columns = configured.append
    view.status_label = types.SimpleNamespace(
        configure=lambda **kwargs: statuses.append(kwargs["text"]))
    rows = [(1, "time"), (2, "later")]
    monkeypatch.setattr(
        payload_view_module,
        "collect_payload_rows",
        lambda editor, parent, received:
        (["field"], rows) if received is definition else pytest.fail(
            "wrong definition"),
    )

    view._on_definition_selected()

    assert deleted == [("stale",)]
    assert configured == [("field",)]
    assert inserted == [
        (("", "end"), {"values": rows[0]}),
        (("", "end"), {"values": rows[1]}),
    ]
    assert statuses == ["2 matching packet(s)"]
