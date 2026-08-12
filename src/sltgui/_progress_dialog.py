"""Reusable progress dialog for background operations."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TypeVar, cast

Result = TypeVar("Result")


class OperationCanceledError(Exception):
    """Raised when a user cancels an in-progress operation."""


def run_with_progress(
    parent: tk.Misc,
    title: str,
    worker_fn: Callable[[Callable[[float], None]], Result],
) -> Result:
    """Run work in a background thread while displaying modal progress."""
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text=title).pack(anchor=tk.W)
    progress_bar = ttk.Progressbar(frame,
                                   mode="determinate",
                                   maximum=100,
                                   length=280)
    progress_bar.pack(fill=tk.X, pady=(8, 0))
    percent_text = tk.StringVar(parent, "0%")
    ttk.Label(frame, textvariable=percent_text).pack(anchor=tk.E, pady=(6, 0))
    cancel_button = ttk.Button(frame, text="Cancel")
    cancel_button.pack(anchor=tk.E, pady=(8, 0))

    cancel_requested = threading.Event()
    updates: queue.Queue[tuple[str, object]] = queue.Queue()
    results: list[Result] = []
    errors: list[BaseException] = []

    def request_cancel() -> None:
        cancel_requested.set()
        cancel_button.configure(state=tk.DISABLED)
        percent_text.set("Cancelling...")

    cancel_button.configure(command=request_cancel)
    dialog.protocol("WM_DELETE_WINDOW", request_cancel)

    def progress_callback(progress: float) -> None:
        if cancel_requested.is_set():
            raise OperationCanceledError("Operation cancelled.")
        updates.put(("progress", progress))

    def worker() -> None:
        try:
            updates.put(("result", worker_fn(progress_callback)))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            updates.put(("error", exc))

    dialog.update_idletasks()
    _center_dialog(dialog)
    dialog.deiconify()
    dialog.grab_set()
    dialog.update()
    done_var = tk.BooleanVar(parent, False)

    def poll_updates() -> None:
        done = False
        while True:
            try:
                kind, payload = updates.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                percent = int(max(0.0, min(1.0, float(payload))) * 100)
                if percent > progress_bar["value"]:
                    progress_bar["value"] = percent
                    percent_text.set(f"{percent}%")
            elif kind == "result":
                results.append(cast(Result, payload))
                done = True
            elif kind == "error":
                errors.append(cast(BaseException, payload))
                done = True
        if done:
            done_var.set(True)
        else:
            dialog.after(15, poll_updates)

    threading.Thread(target=worker, daemon=True).start()
    dialog.after(0, poll_updates)
    parent.wait_variable(done_var)

    if dialog.winfo_exists():
        if not errors:
            progress_bar["value"] = 100
            percent_text.set("100%")
        dialog.update_idletasks()
        dialog.grab_release()
        dialog.destroy()

    if errors:
        raise errors[0]
    return results[0]


def _center_dialog(dialog: tk.Toplevel) -> None:
    """Center a dialog over its parent window."""
    parent = dialog.master
    dialog.update_idletasks()
    width = dialog.winfo_reqwidth()
    height = dialog.winfo_reqheight()
    pos_x = parent.winfo_rootx() + max((parent.winfo_width() - width) // 2, 0)
    pos_y = parent.winfo_rooty() + max(
        (parent.winfo_height() - height) // 2,
        0,
    )
    dialog.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
