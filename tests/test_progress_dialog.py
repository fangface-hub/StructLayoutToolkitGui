"""Tests for the shared progress dialog runner."""
import types

import pytest

import sltgui._progress_dialog as progress_module


class _Variable:

    def __init__(self, _parent, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Parent:

    def __init__(self):
        self.callbacks = []

    def wait_variable(self, variable):
        while not variable.get():
            self.callbacks.pop(0)()

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 200

    def winfo_width(self):
        return 500

    def winfo_height(self):
        return 400


class _Widget:

    def __init__(self, _parent=None, **_kwargs):
        self.options = {}

    def pack(self, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.options.update(kwargs)


class _Progressbar(_Widget):
    instances = []

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.options["value"] = 0
        self.__class__.instances.append(self)

    def __getitem__(self, key):
        return self.options[key]

    def __setitem__(self, key, value):
        self.options[key] = value


class _Button(_Widget):
    instances = []

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.command = None
        self.__class__.instances.append(self)

    def configure(self, **kwargs):
        super().configure(**kwargs)
        self.command = kwargs.get("command", self.command)


class _Dialog(_Widget):
    instances = []

    def __init__(self, parent):
        super().__init__(parent)
        self.master = parent
        self.exists = True
        self.geometry_value = None
        self.close_command = None
        self.__class__.instances.append(self)

    def withdraw(self):
        return None

    def title(self, _title):
        return None

    def transient(self, _parent):
        return None

    def resizable(self, _width, _height):
        return None

    def protocol(self, _name, command):
        self.close_command = command

    def update_idletasks(self):
        return None

    def deiconify(self):
        return None

    def grab_set(self):
        return None

    def update(self):
        return None

    def after(self, _delay, callback):
        self.master.callbacks.append(callback)

    def winfo_exists(self):
        return self.exists

    def winfo_reqwidth(self):
        return 300

    def winfo_reqheight(self):
        return 100

    def geometry(self, value):
        self.geometry_value = value

    def grab_release(self):
        return None

    def destroy(self):
        self.exists = False


class _Thread:
    cancel_before_start = False

    def __init__(self, *, target, daemon):
        assert daemon is True
        self.target = target

    def start(self):
        if self.cancel_before_start:
            _Button.instances[-1].command()
        self.target()


@pytest.fixture(name="progress_stubs")
def fixture_progress_stubs(monkeypatch):
    _Progressbar.instances.clear()
    _Button.instances.clear()
    _Dialog.instances.clear()
    _Thread.cancel_before_start = False
    monkeypatch.setattr(progress_module.tk, "Toplevel", _Dialog)
    monkeypatch.setattr(progress_module.tk, "StringVar", _Variable)
    monkeypatch.setattr(progress_module.tk, "BooleanVar", _Variable)
    monkeypatch.setattr(progress_module.ttk, "Frame", _Widget)
    monkeypatch.setattr(progress_module.ttk, "Label", _Widget)
    monkeypatch.setattr(progress_module.ttk, "Progressbar", _Progressbar)
    monkeypatch.setattr(progress_module.ttk, "Button", _Button)
    monkeypatch.setattr(progress_module.threading, "Thread", _Thread)
    return types.SimpleNamespace(parent=_Parent())


def test_run_with_progress_returns_result_and_completes_dialog(progress_stubs):

    def worker(report_progress):
        report_progress(0.4)
        report_progress(0.2)
        return "result"

    result = progress_module.run_with_progress(progress_stubs.parent,
                                               "Working...", worker)

    assert result == "result"
    assert _Progressbar.instances[-1]["value"] == 100
    assert _Dialog.instances[-1].geometry_value == "300x100+200+350"
    assert not _Dialog.instances[-1].exists


def test_run_with_progress_propagates_worker_error(progress_stubs):

    def worker(_report_progress):
        raise ValueError("failed")

    with pytest.raises(ValueError, match="failed"):
        progress_module.run_with_progress(progress_stubs.parent, "Working...",
                                          worker)

    assert not _Dialog.instances[-1].exists


def test_run_with_progress_raises_when_cancelled(progress_stubs):
    _Thread.cancel_before_start = True

    def worker(report_progress):
        report_progress(0.5)

    with pytest.raises(progress_module.OperationCanceledError,
                       match="cancelled"):
        progress_module.run_with_progress(progress_stubs.parent, "Working...",
                                          worker)

    assert _Button.instances[-1].options["state"] == progress_module.tk.DISABLED
