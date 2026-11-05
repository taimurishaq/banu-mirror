"""Windows helpers: start/stop helper programs, firewall and network checks."""

import ctypes
import os
import subprocess
import threading

CREATE_NO_WINDOW = 0x08000000
CTRL_C_EVENT = 0

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_ctrl_lock = threading.Lock()


def start_process(args, env=None, cwd=None):
    """Start a console program with no visible window, reading its output.

    CREATE_NO_WINDOW still gives the program a (hidden) console, which we
    need later to send it Ctrl+C for a clean shutdown.
    """
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        env=env,
        cwd=cwd,
        creationflags=CREATE_NO_WINDOW,
    )


def run_quiet(args, timeout=15, env=None):
    """Run a short command and return (exit_code, output_text)."""
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            env=env,
            stdin=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return -1, "timed out"
    except OSError as exc:
        return -1, str(exc)
    out = (done.stdout or b"") + (done.stderr or b"")
    return done.returncode, out.decode("utf-8", errors="replace")


def send_ctrl_c(pid):
    """Send Ctrl+C to a program running in its own hidden console."""
    with _ctrl_lock:
        _kernel32.FreeConsole()
        if not _kernel32.AttachConsole(pid):
            return False
        try:
            # Ignore the Ctrl+C ourselves while it goes to the other program.
            _kernel32.SetConsoleCtrlHandler(None, True)
            return bool(_kernel32.GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0))
        finally:
            _kernel32.FreeConsole()


def stop_process(proc, grace_seconds=5.0):
    """Ask the program to quit with Ctrl+C, and force it if it doesn't."""
    if proc is None or proc.poll() is not None:
        return
    if send_ctrl_c(proc.pid):
        try:
            proc.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
    proc.kill()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def _powershell(command, timeout=30):
    return run_quiet(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        timeout=timeout,
    )


def firewall_allows(program_path):
    """True/False if an enabled inbound Allow rule exists for this program.

    Returns None if the check itself failed.
    """
    path = str(program_path).replace("'", "''")
    cmd = (
        "$p = '%s'; "
        "$f = Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Program -eq $p }; "
        "$ok = $f | Get-NetFirewallRule -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }; "
        "if ($ok) { 'YES' } else { 'NO' }" % path
    )
    code, out = _powershell(cmd)
    if code != 0:
        return None
    return "YES" in out


def public_networks():
    """Names of connected networks that Windows treats as Public."""
    code, out = _powershell(
        "Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } | "
        "ForEach-Object { $_.Name }"
    )
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def bonjour_running():
    code, out = _powershell(
        "(Get-Service -Name 'Bonjour Service' -ErrorAction SilentlyContinue).Status"
    )
    return code == 0 and "Running" in out


def add_firewall_rule_elevated(program_path, rule_name):
    """Open an admin PowerShell (Windows asks Yes/No) that adds the rule."""
    path = str(program_path).replace("'", "''")
    name = rule_name.replace("'", "''")
    command = (
        "New-NetFirewallRule -DisplayName '%s' -Direction Inbound -Program '%s' "
        "-Action Allow -Profile Private -Protocol Any | Out-Null" % (name, path)
    )
    params = '-NoProfile -WindowStyle Hidden -Command "%s"' % command
    result = _shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 0)
    return result > 32  # Windows returns <= 32 when the user says No or it fails


def open_path(path):
    os.startfile(str(path))
