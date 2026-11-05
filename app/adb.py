"""Small wrappers around adb (Android Debug Bridge)."""

import re
from dataclasses import dataclass

from winproc import run_quiet


@dataclass
class Device:
    serial: str
    state: str  # "device", "unauthorized", "offline", ...
    model: str

    @property
    def wifi(self):
        return ":" in self.serial or "._adb-tls-connect." in self.serial

    @property
    def label(self):
        return self.model.replace("_", " ") if self.model else "Android phone"


def devices(adb):
    code, out = run_quiet([str(adb), "devices", "-l"], timeout=20)
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("*"):
            continue
        model = ""
        for p in parts[2:]:
            if p.startswith("model:"):
                model = p[6:]
        found.append(Device(parts[0], parts[1], model))
    return found


def mdns_services(adb):
    """Return {'pairing': [addr...], 'connect': [addr...]} seen on the network."""
    code, out = run_quiet([str(adb), "mdns", "services"], timeout=15)
    result = {"pairing": [], "connect": []}
    for line in out.splitlines():
        m = re.search(r"_adb-tls-(pairing|connect)\._tcp\.?\s+(\d+\.\d+\.\d+\.\d+:\d+)", line)
        if m:
            result[m.group(1)].append(m.group(2))
    return result


def connect(adb, address):
    code, out = run_quiet([str(adb), "connect", address], timeout=15)
    return "connected to" in out, out.strip()


def pair(adb, address, code):
    rc, out = run_quiet([str(adb), "pair", address, code], timeout=30)
    return "Successfully paired" in out, out.strip()


def kill_server(adb):
    run_quiet([str(adb), "kill-server"], timeout=10)


def pick_usb(adb):
    """Return (device, problem_message)."""
    usb = [d for d in devices(adb) if not d.wifi]
    ready = [d for d in usb if d.state == "device"]
    if ready:
        return ready[0], ""
    if any(d.state == "unauthorized" for d in usb):
        return None, ("Your phone is asking for permission.\n\n"
                      "Unlock the phone and tap Allow on \"Allow USB debugging?\", then press Start again.")
    return None, ("No phone found on the USB cable.\n\n"
                  "1. Plug the phone in with a data USB cable.\n"
                  "2. On the phone: Settings > System > Developer options > USB debugging = On.\n"
                  "3. Tap Allow if the phone asks.")


def pick_wifi(adb):
    """Find a paired phone over Wi-Fi, connecting to it if needed."""

    def ready_wifi():
        found = [d for d in devices(adb) if d.wifi and d.state == "device"]
        # Prefer the plain IP:port entry when the same phone is listed twice.
        found.sort(key=lambda d: 0 if ":" in d.serial and "._adb" not in d.serial else 1)
        return found

    found = ready_wifi()
    if found:
        return found[0], ""
    for address in mdns_services(adb)["connect"]:
        connect(adb, address)
    found = ready_wifi()
    if found:
        return found[0], ""
    return None, ("Can't find your phone over Wi-Fi.\n\n"
                  "1. The phone and this laptop must be on the same Wi-Fi.\n"
                  "2. On the phone: Developer options > Wireless debugging = On.\n"
                  "3. First time on this laptop? Click \"Pair phone…\" first.")
