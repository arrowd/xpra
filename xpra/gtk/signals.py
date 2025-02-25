# This file is part of Xpra.
# Copyright (C) 2011-2024 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

import signal
from collections.abc import Callable

from xpra.os_util import POSIX, gi_import
from xpra.util.system import SIGNAMES
from xpra.util.io import stderr_print, get_util_logger

_glib_unix_signals: dict[int, int] = {}


def quit_on_signals(commandtype: str = ""):
    gtk = gi_import("Gtk")

    def signal_handler(signum: int):
        gtk.main_quit()

    register_os_signals(signal_handler, commandtype)


def register_os_signals(callback: Callable[[int], None],
                        commandtype: str = "",
                        signals=(signal.SIGINT, signal.SIGTERM)):
    for signum in signals:
        register_os_signal(callback, commandtype, signum)


def register_os_signal(callback: Callable[[int], None], commandtype: str = "", signum: signal.Signals = signal.SIGINT):
    glib = gi_import("GLib")
    signame = SIGNAMES.get(signum, str(signum))

    def write_signal() -> None:
        if not commandtype:
            return
        try:
            stderr_print()
            cstr = ""
            if commandtype:
                cstr = commandtype + " "
            get_util_logger().info(f"{cstr}got signal {signame}")
        except OSError:
            pass

    def do_handle_signal() -> None:
        callback(int(signum))

    if POSIX:
        # replace the previous definition if we had one:
        current = _glib_unix_signals.get(signum, None)
        if current:
            glib.source_remove(current)

        def handle_signal(_signum) -> bool:
            write_signal()
            glib.idle_add(do_handle_signal)
            return True

        source_id = glib.unix_signal_add(glib.PRIORITY_HIGH, signum, handle_signal, signum)
        _glib_unix_signals[signum] = source_id
    else:
        def os_signal(_signum, _frame) -> None:
            write_signal()
            glib.idle_add(do_handle_signal)

        signal.signal(signum, os_signal)


def register_SIGUSR_signals(commandtype: str = "Server"):
    if not POSIX:
        return
    from xpra.util.pysystem import dump_all_frames, dump_gc_frames
    log = get_util_logger()

    def sigusr1(_sig):
        log.info("SIGUSR1")
        dump_all_frames(log.info)
        return True

    def sigusr2(*_args):
        log.info("SIGUSR2")
        dump_gc_frames(log.info)
        return True

    register_os_signals(sigusr1, commandtype, (signal.SIGUSR1,))
    register_os_signals(sigusr2, commandtype, (signal.SIGUSR2,))


def install_signal_handlers(sstr: str, signal_handler: Callable[[int], None]):
    # only register the glib signal handler
    # once the main loop is running,
    # before that we just trigger a KeyboardInterrupt
    def do_install_signal_handlers():
        register_os_signals(signal_handler, sstr)
        register_SIGUSR_signals(sstr)

    glib = gi_import("GLib")
    glib.idle_add(do_install_signal_handlers)
