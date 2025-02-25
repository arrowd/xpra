# This file is part of Xpra.
# Copyright (C) 2018-2024 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

import os
from time import sleep
from textwrap import wrap

from xpra.os_util import gi_import, POSIX, OSX, WIN32
from xpra.util.env import envint
from xpra.util.str_fn import csv
from xpra.util.thread import start_thread
from xpra.gtk.configure.common import DISCLAIMER, run_gui, get_config_env, update_config_env
from xpra.gtk.dialogs.base_gui_window import BaseGUIWindow
from xpra.gtk.widget import label, setfont
from xpra.platform.paths import get_image
from xpra.log import Logger

Gtk = gi_import("Gtk")
GLib = gi_import("GLib")

log = Logger("gstreamer", "util")

STEP_DELAY = envint("XPRA_CONFIGURE_STEP_DELAY", 100)


def _set_labels_text(widgets, *messages):
    for i, widget in enumerate(widgets):
        if i < len(messages):
            widget.set_text(messages[i])
        else:
            widget.set_text("")


class ConfigureGUI(BaseGUIWindow):

    def __init__(self, parent: Gtk.Window | None = None):
        self.warning_pixbuf = get_image("warning.png")
        size = (800, 554)
        if self.warning_pixbuf:
            size = self.warning_pixbuf.get_width() + 20, self.warning_pixbuf.get_height() + 20
        self.layout = None
        self.warning_labels = []
        self.labels = []
        self.buttons = []
        self.elements = []
        super().__init__(
            "Configure Xpra's GStreamer Codecs",
            "gstreamer.png",
            wm_class=("xpra-configure-gstreamer-gui", "Xpra Configure GStreamer GUI"),
            default_size=size,
            header_bar=(False, False),
            parent=parent,
        )
        self.set_resizable(False)

    def add_layout(self) -> None:
        if not self.layout:
            layout = Gtk.Layout()
            layout.set_margin_top(0)
            layout.set_margin_bottom(0)
            layout.set_margin_start(0)
            layout.set_margin_end(0)
            self.layout = layout
            self.vbox.add(layout)

    def populate(self) -> None:
        self.set_box_margin(0, 0, 0, 0)
        self.add_layout()
        if self.warning_pixbuf:
            image = Gtk.Image.new_from_pixbuf(self.warning_pixbuf)
            self.layout.put(image, 0, 0)
        for i in range(3):
            lbl = label("", font="Sans 22")
            self.warning_labels.append(lbl)
            self.layout.put(lbl, 86, 70 + i * 40)
        for i in range(11):
            lbl = label("", font="Sans 12")
            self.layout.put(lbl, 78, 180 + i * 24)
            self.labels.append(lbl)

        self.set_warning_labels(
            "This tool can cause your system to crash,",
            "it may even damage hardware in rare cases.",
            "            Use with caution.",
        )
        self.set_labels("", "", *wrap(DISCLAIMER))
        self.add_buttons(
            ("Understood", self.detect_elements),
            ("Get me out of here", self.dismiss)
        )

    def set_warning_labels(self, *messages) -> None:
        _set_labels_text(self.warning_labels, *messages)

    def set_labels(self, *messages) -> None:
        _set_labels_text(self.labels, *messages)

    def add_buttons(self, *buttons) -> None:
        # remove existing buttons:
        for button in self.buttons:
            self.layout.remove(button)
        i = 0
        x = 400 - 100 * len(buttons)
        for text, callback in buttons:
            button = Gtk.Button.new_with_label(text)
            button.connect("clicked", callback)
            button.show()
            self.buttons.append(button)
            self.layout.put(button, x + 200 * i, 450)
            i += 1

    def detect_elements(self, *_args) -> None:
        self.set_warning_labels(
            "Probing the GStreamer elements available,",
            "please wait.",
        )
        self.set_labels()
        self.add_buttons(("Abort and exit", self.dismiss))
        messages = []

        def update_messages():
            sleep(STEP_DELAY / 1000)
            GLib.idle_add(self.set_labels, *messages)

        def add_message(msg):
            messages.append(msg)
            update_messages()

        def update_message(msg: str) -> None:
            messages[-1] = msg
            update_messages()

        def probe_elements() -> None:
            add_message("Loading the GStreamer bindings")
            try:
                gst = gi_import("Gst")
                update_message("loaded the GStreamer bindings")
                add_message("initializing GStreamer")
                gst.init(None)
                update_message("initialized GStreamer")
            except Exception as e:
                log("Warning failed to import GStreamer", exc_info=True)
                update_message(f"Failed to load GStreamer: {e}")
                return
            try:
                add_message("locating plugins")
                from xpra.gstreamer.common import import_gst, get_all_plugin_names
                import_gst()
                self.elements = get_all_plugin_names()
                update_message(f"found {len(self.elements)} elements")
            except Exception as e:
                log("Warning failed to load GStreamer plugins", exc_info=True)
                update_message(f"Failed to load plugins: {e}")
                return
            if not self.elements:
                update_message("no elements found - cannot continue")
                return
            pset = set(self.elements)
            need = {"capsfilter", "videoconvert", "videoscale", "queue"}
            missing = tuple(need - pset)
            if missing:
                add_message("some essential plugins are missing: " + csv(missing))
                add_message("install them then you can run this tool again")
                return
            add_message("essential plugins found")
            want = {"x264enc", "vp8enc", "vp9enc", "webmmux"}
            found = tuple(want & pset)
            if not found:
                add_message("install at least one plugin from: " + csv(want))
                add_message("then you can run this tool again")
                return
            missing = tuple(want - pset)
            if missing:
                add_message("some useful extra plugins you may want to install: " + csv(missing))
            if not (WIN32 or OSX) and "pipewiresrc" not in pset:
                add_message("`pipewiresrc` is missing - it is required for shadowing Wayland sessions")

            GLib.timeout_add(STEP_DELAY * 6, self.add_buttons,
                             ("configure shadow mode", self.configure_shadow),
                             # ("configure encoding", self.configure_encoding),
                             # ("configure decoding", self.configure_decoding),
                             )

        start_thread(probe_elements, "probe-elements", daemon=True)

    def configure_encoding(self, *_args) -> None:
        pass

    def configure_decoding(self, *_args) -> None:
        pass

    def configure_shadow(self, *_args) -> None:
        self.clear_vbox()
        self.set_box_margin()
        self.layout = None
        messages = (
            "Configuring shadow mode",
        )

        def has(*els):
            return all(el in self.elements for el in els)

        backends = []
        if POSIX and not OSX:
            from xpra.platform.posix.shadow_server import SHADOW_OPTIONS
            backends = SHADOW_OPTIONS
            options = (
                (
                    True, "auto", "Automatic runtime detection",
                    "this is the default behaviour",
                    "this option should always find a suitable capture strategy",
                    "it may not to use a video stream",
                ),
                (
                    has("ximagesrc"), "X11", "X11 image capture",
                    "GStreamer will capture the session's contents using 'ximagesrc'",
                    "the pixel data will be compressed using a stream encoder",
                    "eg: h264, hevc, av1, etc",
                    "this option is only available for shadowing existing X11 sessions",
                ),
                (
                    has("pipewiresrc"), "pipewire", "pipewire capture",
                    "GStreamer use a pipewire source from the RemoteDesktop interface",
                    "the pixel data will be compressed using a stream encoder",
                    "eg: h264, hevc, av1, etc",
                    "your desktop sessions must support the 'RemoteDesktop' dbus interface",
                ),
            )
        else:
            raise RuntimeError(f"unsupported platform {os.name}")
        for i, message in enumerate(messages):
            lbl = label(message, font="Sans 22")
            self.vbox.add(lbl)
        current_setting = get_config_env("XPRA_SHADOW_BACKEND")
        self.buttons = []
        for available, backend, description, *details in options:
            btn = Gtk.CheckButton(label=description)
            btn.set_sensitive(available)
            btn.set_active(backend == current_setting)
            btn._backend = backend
            setfont(btn, font="sans 14")
            self.vbox.add(btn)
            for detail in details:
                lbl = label(detail)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_start(32)
                self.vbox.add(lbl)
            self.buttons.append(btn)
        btn_box = Gtk.HBox(homogeneous=True, spacing=40)
        btn_box.set_vexpand(True)
        btn_box.set_valign(Gtk.Align.END)
        self.vbox.add(btn_box)
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        cancel_btn.connect("clicked", self.dismiss)
        btn_box.add(cancel_btn)
        confirm_btn = Gtk.Button.new_with_label("Confirm")

        def save_shadow(*_args):
            active = [button for button in self.buttons if button.get_active()]
            assert len(active) == 1
            setting = active[0]._backend.lower()
            if setting not in backends:
                raise RuntimeError(f"invalid backend selected: {setting}")
            log.info(f"saving XPRA_SHADOW_BACKEND={setting}")
            update_config_env("XPRA_SHADOW_BACKEND", setting)
            self.dismiss()

        confirm_btn.connect("clicked", save_shadow)
        confirm_btn.set_sensitive(False)
        btn_box.add(confirm_btn)

        # only enable the confirm button once an option has been chosen:
        def option_toggled(toggled_btn, *_args):
            if toggled_btn.get_active():
                for button in self.buttons:
                    if button != toggled_btn:
                        button.set_active(False)
            confirm_btn.set_sensitive(any(button.get_active() for button in self.buttons))

        for btn in self.buttons:
            btn.connect("toggled", option_toggled)
        self.vbox.show_all()


def main(_args) -> int:
    return run_gui(ConfigureGUI)


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
