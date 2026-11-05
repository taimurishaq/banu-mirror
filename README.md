# Banu mirror

A small Windows app for mirroring a phone or tablet screen to a laptop:

- **iPad / iPhone** over Wi-Fi, using UxPlay (an open-source AirPlay-compatible receiver)
- **Android (Pixel)** over USB or Wi-Fi, using scrcpy

## Download and install

1. Go to the [**Releases page**](https://github.com/taimurishaq/banu-mirror/releases/latest)
   and download **`BanuMirror-Setup-x.x.x.exe`**.
2. Double-click it. When Windows asks *"Do you want to allow this app to make changes?"*, click **Yes**.
   (Admin permission lets the installer allow the app through Windows Firewall.)
3. Click **Next** → **Install** → **Finish**.

Needs Windows 10 or 11 (64-bit). Nothing else to install.

If Windows shows *"Windows protected your PC"*, click **More info** → **Run anyway**.
This appears because the installer isn't signed with a paid certificate.

## Mirror an iPad or iPhone

1. Connect the laptop and the iPad to the **same Wi-Fi**.
   In Windows, set that Wi-Fi to **Private**: Settings → Network & internet → Wi-Fi →
   your network → Network profile type → **Private**.
2. Open **Banu mirror**, choose **iPad / iPhone**, and click **Start**.
3. On the iPad: open **Control Center** → **Screen Mirroring** → choose **Banu mirror**.

Press **Alt+Enter** in the mirror window to switch fullscreen on or off.

## Mirror an Android phone

1. On the phone, turn on **Developer options** and **USB debugging**.
2. Open **Banu mirror** and choose **Android phone**.
   - **USB:** plug in the phone, tap **Allow** on the phone, and click **Start**.
   - **Wi-Fi:** click **Pair phone for Wi-Fi…** and follow the steps in that window.

## For developers

- Set up a development PC: [SETUP-DEV.md](SETUP-DEV.md)
- Build the installer: `py scripts\package.py` (output in `dist\`)

## Credits and licenses

- **UxPlay**: https://github.com/FDH2/UxPlay, licensed under the GNU GPL v3.
  Included unmodified as a Git submodule in `uxplay/`; its license is in `uxplay/LICENSE`.
- **scrcpy**: https://github.com/Genymobile/scrcpy by Genymobile, licensed under Apache-2.0.
- **GStreamer**, **FFmpeg** and other libraries from [MSYS2](https://www.msys2.org) are bundled
  in the installer; their licenses are installed in the `licenses` folder.

Banu mirror is not affiliated with or endorsed by Apple or Google.
AirPlay is a trademark of Apple Inc.
