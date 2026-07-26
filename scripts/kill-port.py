#!/usr/bin/env python3
"""Kill processes occupying the specified ports.

Usage:
    python kill-port.py              # Kill all default service ports
    python kill-port.py 8765 5173    # Kill specific ports only
"""

import subprocess
import sys

# Default service ports (must match the ports in start scripts)
DEFAULT_PORTS = {
    8765: "backend-agent",
    8864: "backend-gateway",
    8010: "backend-data",
    5173: "frontend",
}

IS_WINDOWS = sys.platform == "win32"


def _run(cmd):
    """Run a command, suppressing console window on Windows."""
    kwargs = {"capture_output": True, "text": True, "errors": "replace"}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, **kwargs)
    return result.stdout, result.stderr


def find_pids(port):
    """Return a set of PIDs listening on the given port."""
    if IS_WINDOWS:
        return _find_pids_windows(port)
    return _find_pids_unix(port)


def _find_pids_windows(port):
    stdout, _ = _run(["netstat", "-ano"])
    pids = set()
    suffix = f":{port}"
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        if not local_addr.endswith(suffix):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid != "0":
            pids.add(pid)
    return pids


def _find_pids_unix(port):
    stdout, _ = _run(["lsof", "-i", f":{port}", "-t"])
    pids = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(line)
    return pids


def kill_pid(pid):
    """Force kill a process by PID."""
    if IS_WINDOWS:
        _run(["taskkill", "/PID", pid, "/F"])
    else:
        _run(["kill", "-9", pid])


def kill_port(port, label=""):
    """Find and kill processes on the given port.

    Returns the number of killed processes.
    """
    label_text = f" ({label})" if label else ""
    pids = find_pids(port)
    if not pids:
        print(f"Port {port}{label_text}: no process found")
        return 0
    for pid in sorted(pids):
        kill_pid(pid)
        print(f"Port {port}{label_text}: killed PID {pid}")
    return len(pids)


def main():
    if len(sys.argv) > 1:
        try:
            ports = [(int(arg), "") for arg in sys.argv[1:]]
        except ValueError:
            print("Error: port arguments must be integers")
            sys.exit(1)
    else:
        ports = [(port, label) for port, label in DEFAULT_PORTS.items()]

    print(f"Killing processes on {len(ports)} port(s)...\n")

    total_killed = 0
    for port, label in ports:
        total_killed += kill_port(port, label)

    print(f"\nDone! Killed {total_killed} process(es).")


if __name__ == "__main__":
    main()
