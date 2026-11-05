# Setting up Banu mirror on another PC (for development)

**Just want to use the app?** You don't need any of this. Download the installer from the
[Releases page](https://github.com/taimurishaq/banu-mirror/releases/latest) instead.

These steps get a fresh Windows 10/11 64-bit PC ready to keep building Banu mirror.

## 1. Install the tools

Open a normal PowerShell window and run:

```powershell
winget install --id Git.Git -e
winget install --id MSYS2.MSYS2 -e
winget install --id Genymobile.scrcpy -e
winget install --id Python.Python.3.14 -e
```

Close PowerShell and open a new one afterwards, so the new commands are found.

## 2. Download the project

```powershell
git clone --recurse-submodules https://github.com/taimurishaq/banu-mirror.git
```

`--recurse-submodules` also downloads UxPlay into the `uxplay` folder.
If you forgot it, run `git submodule update --init` inside the project folder.

## 3. Build UxPlay

1. Open **MSYS2 UCRT64** from the Start menu.
2. Go to the project folder. Windows drive `C:` is written `/c/` in MSYS2, for example:
   ```bash
   cd /c/Users/YourName/banu-mirror
   ```
3. Run the setup script:
   ```bash
   bash scripts/setup-dev.sh
   ```
   If the window closes during the first step, MSYS2 updated itself.
   Open **MSYS2 UCRT64** again and run the same command.

When it finishes, `uxplay/build/uxplay.exe` exists.

## 4. Allow it through the firewall

1. Make sure your home Wi-Fi is **Private**: Settings → Network & internet → Wi-Fi → your network → Network profile type → Private.
2. Right-click Start → **Terminal (Admin)** and run (change the path to where you cloned the project):
   ```powershell
   New-NetFirewallRule -DisplayName "UxPlay" -Direction Inbound -Program "C:\Users\YourName\banu-mirror\uxplay\build\uxplay.exe" -Action Allow -Profile Private -Protocol Any
   ```

## 5. Connect the phones again

Each PC needs its own trust from the phones:

- **iPad:** nothing to do.
- **Pixel over USB:** plug it in and tap **Allow** on the phone.
- **Pixel over Wi-Fi:** pair again. Open Developer options → Wireless debugging → Pair device with pairing code, then on the PC run `adb pair <ip:port>` and enter the code.

## 6. Test

In **MSYS2 UCRT64**, from the project folder:

```bash
cd uxplay/build
./uxplay.exe -n "Banu mirror" -nh -p
```

For the Pixel, in PowerShell: `scrcpy -d -m 1280` (USB).

## 7. Start the app

In PowerShell, from the project folder:

```powershell
py app\main.py
```

Use `py`, not `python`, so Windows picks the Python you installed in step 1.

The app expects MSYS2 at `C:\msys64` and scrcpy in winget's default folder,
so keep the default install locations from step 1.
