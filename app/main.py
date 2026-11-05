"""Banu mirror: a small window to mirror an iPad (UxPlay) or Android phone (scrcpy)."""

import ctypes
import json
import queue
import threading
import tkinter as tk
from collections import deque
from tkinter import messagebox, scrolledtext, ttk

import adb
import engines
import winproc
from engines import APP_NAME, CONNECTING, MIRRORING, STARTING, STOPPED, WAITING_IPAD

FIREWALL_RULE_NAME = "Banu mirror (UxPlay)"
STATUS_COLORS = {
    STOPPED: "#8a8a8a",
    STARTING: "#d39b00",
    "Stopping…": "#d39b00",
    WAITING_IPAD: "#1f6fd1",
    CONNECTING: "#d39b00",
    MIRRORING: "#1e9e4a",
}


class Settings:
    DEFAULTS = {
        "device": "ipad",
        "name": APP_NAME,
        "video_engine": "Direct3D 12 (recommended)",
        "connection": "usb",
        "quality": "Balanced",
        "fullscreen": False,
    }

    def __init__(self):
        self.path = engines.data_dir() / "settings.json"
        self.values = dict(self.DEFAULTS)
        try:
            self.values.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            self.path.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        except OSError:
            pass


class App:
    def __init__(self, root):
        self.root = root
        self.settings = Settings()
        self.events = queue.Queue()
        self.proc = None
        self.proc_kind = None  # "ipad" or "android"
        self.watcher = None
        self.recent = deque(maxlen=40)
        self.stopping = False
        self.closing = False

        root.title(APP_NAME)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        s = self.settings.values
        self.device_var = tk.StringVar(value=s["device"])
        self.name_var = tk.StringVar(value=s["name"])
        self.engine_var = tk.StringVar(value=s["video_engine"])
        self.conn_var = tk.StringVar(value=s["connection"])
        self.quality_var = tk.StringVar(value=s["quality"])
        self.fullscreen_var = tk.BooleanVar(value=s["fullscreen"])

        self.build_ui()
        self.on_device_change()
        self.set_status(STOPPED)
        self.root.after(100, self.process_events)
        threading.Thread(target=self.check_system, daemon=True).start()

    # ------------------------------------------------------------ layout

    def build_ui(self):
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self.root, padding=12)
        main.grid(sticky="nsew")

        title = ttk.Label(main, text=APP_NAME, font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w")

        dev = ttk.LabelFrame(main, text="Device")
        dev.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        self.device_buttons = [
            ttk.Radiobutton(dev, text="iPad / iPhone (Wi-Fi)", value="ipad",
                            variable=self.device_var, command=self.on_device_change),
            ttk.Radiobutton(dev, text="Android phone", value="android",
                            variable=self.device_var, command=self.on_device_change),
        ]
        self.device_buttons[0].grid(row=0, column=0, sticky="w", **pad)
        self.device_buttons[1].grid(row=0, column=1, sticky="w", **pad)

        # iPad options
        self.ipad_frame = ttk.LabelFrame(main, text="iPad settings")
        ttk.Label(self.ipad_frame, text="Name shown on iPad:").grid(row=0, column=0, sticky="w", **pad)
        self.name_entry = ttk.Entry(self.ipad_frame, textvariable=self.name_var, width=26)
        self.name_entry.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(self.ipad_frame, text="Video engine:").grid(row=1, column=0, sticky="w", **pad)
        self.engine_box = ttk.Combobox(self.ipad_frame, textvariable=self.engine_var, state="readonly",
                                       values=list(engines.VIDEO_ENGINES), width=24)
        self.engine_box.grid(row=1, column=1, sticky="w", **pad)

        # Android options
        self.android_frame = ttk.LabelFrame(main, text="Android settings")
        ttk.Label(self.android_frame, text="Connect by:").grid(row=0, column=0, sticky="w", **pad)
        conn = ttk.Frame(self.android_frame)
        conn.grid(row=0, column=1, sticky="w", **pad)
        self.conn_buttons = [
            ttk.Radiobutton(conn, text="USB cable (fastest)", value="usb", variable=self.conn_var),
            ttk.Radiobutton(conn, text="Wi-Fi", value="wifi", variable=self.conn_var),
        ]
        self.conn_buttons[0].grid(row=0, column=0, sticky="w")
        self.conn_buttons[1].grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.pair_button = ttk.Button(self.android_frame, text="Pair phone for Wi-Fi…", command=self.open_pair_dialog)
        self.pair_button.grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(self.android_frame, text="Quality:").grid(row=2, column=0, sticky="w", **pad)
        self.quality_box = ttk.Combobox(self.android_frame, textvariable=self.quality_var, state="readonly",
                                        values=list(engines.QUALITY_PRESETS), width=12)
        self.quality_box.grid(row=2, column=1, sticky="w", **pad)

        self.options_row = 2
        self.fullscreen_check = ttk.Checkbutton(main, text="Start in fullscreen", variable=self.fullscreen_var)
        self.fullscreen_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.hint = ttk.Label(main, foreground="#555555", wraplength=380, justify="left")
        self.hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(main)
        buttons.grid(row=5, column=0, columnspan=2, sticky="w")
        self.start_button = ttk.Button(buttons, text="Start", command=self.start, width=12)
        self.start_button.grid(row=0, column=0)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, width=12)
        self.stop_button.grid(row=0, column=1, padx=(8, 0))

        status = ttk.Frame(main)
        status.grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.dot = tk.Canvas(status, width=14, height=14, highlightthickness=0)
        self.dot_item = self.dot.create_oval(2, 2, 12, 12, fill="#8a8a8a", outline="")
        self.dot.grid(row=0, column=0)
        self.status_label = ttk.Label(status, text=STOPPED, font=("Segoe UI", 11, "bold"))
        self.status_label.grid(row=0, column=1, padx=(6, 0))

        self.warn_frame = ttk.Frame(main)
        self.warn_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.details_button = ttk.Button(main, text="Show details ▾", command=self.toggle_details)
        self.details_button.grid(row=8, column=0, sticky="w", pady=(10, 0))
        self.log = scrolledtext.ScrolledText(main, width=62, height=12, font=("Consolas", 9), state="disabled")
        self.log_visible = False

    def on_device_change(self):
        ipad = self.device_var.get() == "ipad"
        if ipad:
            self.android_frame.grid_forget()
            self.ipad_frame.grid(row=self.options_row, column=0, columnspan=2, sticky="ew", pady=4)
            self.hint.config(text="On the iPad: Control Center → Screen Mirroring → choose the name above.\n"
                                  "Press Alt+Enter in the video window to switch fullscreen on/off.")
        else:
            self.ipad_frame.grid_forget()
            self.android_frame.grid(row=self.options_row, column=0, columnspan=2, sticky="ew", pady=4)
            self.hint.config(text="Press Alt+F (or F11) in the phone window to switch fullscreen on/off.\n"
                                  "You can use the mouse and keyboard to control the phone.")

    def open_pair_dialog(self):
        found = engines.find_scrcpy()
        if not found[0]:
            messagebox.showerror(APP_NAME, found[1])
            return
        PairDialog(self.root, found[1])

    def toggle_details(self):
        if self.log_visible:
            self.log.grid_forget()
            self.details_button.config(text="Show details ▾")
        else:
            self.log.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            self.details_button.config(text="Hide details ▴")
        self.log_visible = not self.log_visible

    def set_controls(self, running):
        state = "disabled" if running else "normal"
        for w in self.device_buttons + self.conn_buttons + [self.name_entry, self.fullscreen_check, self.pair_button]:
            w.config(state=state)
        for box in (self.engine_box, self.quality_box):
            box.config(state="disabled" if running else "readonly")
        self.start_button.config(state="disabled" if running else "normal")
        self.stop_button.config(state="normal" if running else "disabled")

    def set_status(self, status, text=None):
        self.status_label.config(text=text or status)
        self.dot.itemconfig(self.dot_item, fill=STATUS_COLORS.get(status, "#8a8a8a"))

    def append_log(self, line):
        self.log.config(state="normal")
        self.log.insert("end", line + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 600:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.config(state="disabled")

    # ------------------------------------------------------------ system checks

    def check_system(self):
        warnings = []
        exe, env_or_reason = engines.find_uxplay()
        if exe:
            allowed = winproc.firewall_allows(exe)
            if allowed is False:
                warnings.append(("firewall", "Windows Firewall may block the iPad from connecting.", exe))
        nets = winproc.public_networks()
        if nets:
            warnings.append(("public", "Your network \"%s\" is set to Public. Set it to Private in "
                                       "Settings → Network & internet → Wi-Fi so the iPad can find this PC."
                             % ", ".join(nets), None))
        if winproc.bonjour_running():
            warnings.append(("bonjour", "Apple's Bonjour service is running. If the iPad can't see "
                                        "Banu mirror, stop \"Bonjour Service\" in services.msc.", None))
        self.events.put(("warnings", warnings))

    def show_warnings(self, warnings):
        for child in self.warn_frame.winfo_children():
            child.destroy()
        for row, (kind, text, exe) in enumerate(warnings):
            box = tk.Frame(self.warn_frame, bg="#fff4d6", padx=8, pady=6)
            box.grid(row=row, column=0, sticky="ew", pady=2)
            tk.Label(box, text="⚠ " + text, bg="#fff4d6", wraplength=330, justify="left").grid(row=0, column=0, sticky="w")
            if kind == "firewall":
                ttk.Button(box, text="Allow…", command=lambda e=exe: self.fix_firewall(e)).grid(row=0, column=1, padx=(8, 0))

    def fix_firewall(self, exe):
        if winproc.add_firewall_rule_elevated(exe, FIREWALL_RULE_NAME):
            self.root.after(4000, lambda: threading.Thread(target=self.check_system, daemon=True).start())
        else:
            messagebox.showwarning(APP_NAME, "The firewall rule was not added (Windows permission was declined).")

    # ------------------------------------------------------------ start / stop

    def save_settings(self):
        self.settings.values.update({
            "device": self.device_var.get(),
            "name": self.name_var.get().strip() or APP_NAME,
            "video_engine": self.engine_var.get(),
            "connection": self.conn_var.get(),
            "quality": self.quality_var.get(),
            "fullscreen": bool(self.fullscreen_var.get()),
        })
        self.settings.save()

    def start(self):
        if self.proc:
            return
        self.save_settings()
        self.recent.clear()
        self.set_controls(True)
        self.set_status(STARTING)
        kind = self.device_var.get()
        target = self.prepare_ipad if kind == "ipad" else self.prepare_android
        threading.Thread(target=target, daemon=True).start()

    def prepare_ipad(self):
        exe, env = engines.find_uxplay()
        if not exe:
            self.events.put(("fail", env))
            return
        engines.ensure_sharp_window(exe)
        name = self.settings.values["name"]
        args = engines.uxplay_args(exe, name, self.settings.values["video_engine"],
                                   self.settings.values["fullscreen"])
        self.launch("ipad", args, env, engines.UxPlayWatcher())

    def prepare_android(self):
        found = engines.find_scrcpy()
        if not found[0]:
            self.events.put(("fail", found[1]))
            return
        scrcpy, adb_exe = found
        self.events.put(("log", "Looking for the phone…"))
        if self.settings.values["connection"] == "usb":
            device, problem = adb.pick_usb(adb_exe)
        else:
            device, problem = adb.pick_wifi(adb_exe)
        if not device:
            self.events.put(("fail", problem))
            return
        args = engines.scrcpy_args(scrcpy, device.serial, self.settings.values["quality"],
                                   self.settings.values["fullscreen"], device.label)
        self.launch("android", args, None, engines.ScrcpyWatcher(), cwd=str(scrcpy.parent))

    def launch(self, kind, args, env, watcher, cwd=None):
        self.events.put(("log", "> " + " ".join('"%s"' % a if " " in a else a for a in args)))
        try:
            proc = winproc.start_process(args, env=env, cwd=cwd)
        except OSError as exc:
            self.events.put(("fail", "Could not start %s:\n%s" % (args[0], exc)))
            return
        self.events.put(("started", (proc, kind, watcher)))
        threading.Thread(target=self.read_output, args=(proc,), daemon=True).start()

    def read_output(self, proc):
        for raw in iter(proc.stdout.readline, b""):
            self.events.put(("line", (proc, raw.decode("utf-8", errors="replace").rstrip())))
        code = proc.wait()
        self.events.put(("exit", (proc, code)))

    def stop(self):
        if not self.proc or self.stopping:
            return
        self.stopping = True
        self.stop_button.config(state="disabled")
        self.set_status("Stopping…")
        proc = self.proc
        threading.Thread(target=winproc.stop_process, args=(proc,), daemon=True).start()

    def on_close(self):
        self.closing = True
        if self.proc:
            self.stop()
        else:
            self.finish_close()

    def finish_close(self):
        found = engines.find_scrcpy()
        if found[0] and engines.app_dir().joinpath("engine").is_dir():
            # Packaged app: stop adb so the folder can be moved or deleted.
            adb.kill_server(found[1])
        self.root.destroy()

    # ------------------------------------------------------------ events from threads

    def process_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                self.handle_event(kind, data)
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def handle_event(self, kind, data):
        if kind == "warnings":
            self.show_warnings(data)
        elif kind == "log":
            self.append_log(data)
        elif kind == "fail":
            self.set_controls(False)
            self.set_status(STOPPED)
            self.append_log("Problem: " + data.replace("\n", " "))
            messagebox.showerror(APP_NAME, data)
        elif kind == "started":
            self.proc, self.proc_kind, self.watcher = data
            self.stopping = False
            self.set_status(self.watcher.status, self.watcher.label())
        elif kind == "line":
            proc, line = data
            if proc is not self.proc or not line:
                return
            self.append_log(line)
            self.recent.append(line)
            if self.watcher.feed(line) is not None:
                self.set_status(self.watcher.status, self.watcher.label())
        elif kind == "exit":
            proc, code = data
            if proc is not self.proc:
                return
            self.on_process_exit(code)

    def on_process_exit(self, code):
        was_stopping = self.stopping
        kind, watcher = self.proc_kind, self.watcher
        self.proc = None
        self.stopping = False
        self.set_controls(False)
        self.set_status(STOPPED)
        self.append_log("(stopped, exit code %s)" % code)
        if self.closing:
            self.finish_close()
            return
        if was_stopping:
            return
        recent = list(self.recent)
        if kind == "ipad" and not watcher.ready:
            reason = engines.explain_uxplay_problem(recent)
            messagebox.showerror(APP_NAME, "UxPlay stopped unexpectedly.\n\n%s\n\nLast messages:\n%s"
                                 % (reason, "\n".join(recent[-12:])))
        elif kind == "android" and code not in (0, None):
            errors = [l for l in recent if "ERROR" in l] or recent[-8:]
            messagebox.showerror(APP_NAME, "scrcpy stopped with a problem:\n\n" + "\n".join(errors[-8:]))


class PairDialog:
    """One-time Wi-Fi pairing with the phone's 'Pair device with pairing code' screen."""

    def __init__(self, parent, adb_exe):
        self.adb = adb_exe
        self.auto_address = ""
        self.closed = False
        self.win = tk.Toplevel(parent)
        self.win.title("Pair phone for Wi-Fi")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        f = ttk.Frame(self.win, padding=14)
        f.grid()
        steps = ("On the phone (same Wi-Fi as this laptop):\n"
                 "1. Settings > System > Developer options > Wireless debugging = On\n"
                 "2. Tap \"Wireless debugging\", then \"Pair device with pairing code\"\n"
                 "3. Keep that popup open and type its 6-digit code below")
        ttk.Label(f, text=steps, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="Pairing address:").grid(row=1, column=0, sticky="w", pady=(12, 4))
        self.address_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.address_var, width=24).grid(row=1, column=1, sticky="w", pady=(12, 4))
        ttk.Label(f, text="6-digit code:").grid(row=2, column=0, sticky="w", pady=4)
        self.code_var = tk.StringVar()
        code_entry = ttk.Entry(f, textvariable=self.code_var, width=10)
        code_entry.grid(row=2, column=1, sticky="w", pady=4)
        self.info = ttk.Label(f, text="Looking for the phone's pairing popup…", foreground="#555555", wraplength=380)
        self.info.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 8))
        row = ttk.Frame(f)
        row.grid(row=4, column=0, columnspan=2, sticky="e")
        self.pair_button = ttk.Button(row, text="Pair", command=self.do_pair)
        self.pair_button.grid(row=0, column=0)
        ttk.Button(row, text="Close", command=self.close).grid(row=0, column=1, padx=(8, 0))
        code_entry.focus_set()
        # Background threads put results here; the window reads them (Tkinter
        # must only be touched from the main thread).
        self.results = queue.Queue()
        self.poll()
        self.scan()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                handler, args = self.results.get_nowait()
                handler(*args)
        except queue.Empty:
            pass
        self.win.after(150, self.poll)

    def scan(self):
        """Look for the phone's pairing service every few seconds."""
        if self.closed:
            return

        def work():
            found = adb.mdns_services(self.adb)["pairing"]
            self.results.put((self.on_scan, (found,)))

        threading.Thread(target=work, daemon=True).start()

    def on_scan(self, found):
        if self.closed:
            return
        current = self.address_var.get().strip()
        if found and (not current or current == self.auto_address):
            self.auto_address = found[0]
            self.address_var.set(found[0])
            self.info.config(text="Found the phone. Type the code and click Pair.")
        elif not found and not current:
            self.info.config(text="Looking for the phone's pairing popup… "
                                  "(or type the IP address & port shown in the popup)")
        self.win.after(3000, self.scan)

    def do_pair(self):
        address = self.address_var.get().strip()
        code = self.code_var.get().strip().replace(" ", "")
        if not address or not code.isdigit() or len(code) != 6:
            messagebox.showwarning("Pair phone", "Enter the pairing address and the 6-digit code.", parent=self.win)
            return
        self.pair_button.config(state="disabled")
        self.info.config(text="Pairing…")

        def work():
            ok, out = adb.pair(self.adb, address, code)
            if ok:
                for addr in adb.mdns_services(self.adb)["connect"]:
                    adb.connect(self.adb, addr)
            self.results.put((self.on_paired, (ok, out)))

        threading.Thread(target=work, daemon=True).start()

    def on_paired(self, ok, out):
        self.pair_button.config(state="normal")
        if ok:
            self.info.config(text="Paired! Close this window, choose Wi-Fi and press Start.", foreground="#1e9e4a")
        else:
            self.info.config(text="Pairing failed: %s\nOpen a fresh pairing popup on the phone and try again."
                                  % (out.splitlines()[-1] if out else "no answer"), foreground="#b00020")

    def close(self):
        self.closed = True
        self.win.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
