"""Windows service lifecycle with a JSON contract compatible with OpenFic's shape.

State is private; callers use the PowerShell entry point rather than its files.
This module deliberately does not import application configuration or the DB.
"""

import argparse
import ctypes
import json
import msvcrt
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
STATE_FILE = "personal-tracker.json"
LOCK_FILE = "personal-tracker.lock"


class ManagementError(Exception):
    def __init__(self, detail: str, state: str = "unknown", *, busy: bool = False):
        super().__init__(detail)
        self.state = state
        self.busy = busy


def process_identity(pid: int) -> dict | None:
    """Use process creation time, not a reusable PID alone, to prove ownership."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # Invalid PID: process has exited.
            return None
        raise ManagementError("Cannot inspect the recorded process identity.")
    try:
        created, exited, kernel_time, user_time = (
            wintypes.FILETIME() for _ in range(4)
        )
        if not kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            raise ManagementError("Cannot read process creation time.")
        if exited.dwLowDateTime or exited.dwHighDateTime:
            return None
        length = wintypes.DWORD(32768)
        executable = ctypes.create_unicode_buffer(length.value)
        if not kernel.QueryFullProcessImageNameW(
            handle, 0, executable, ctypes.byref(length)
        ):
            raise ManagementError("Cannot read the process executable path.")
        return {
            "created": (created.dwHighDateTime << 32) | created.dwLowDateTime,
            "executable": executable.value,
        }
    finally:
        kernel.CloseHandle(handle)


def listeners(port: int) -> set[int]:
    class TcpRow(ctypes.Structure):
        _fields_ = [
            (name, wintypes.DWORD)
            for name in (
                "state",
                "local_address",
                "local_port",
                "remote_address",
                "remote_port",
                "pid",
            )
        ]

    api = ctypes.WinDLL("iphlpapi")
    query = api.GetExtendedTcpTable
    query.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    query.restype = wintypes.DWORD
    size = wintypes.DWORD()
    # AF_INET, TCP_TABLE_OWNER_PID_LISTENER. Unlike parsing netstat output,
    # this API reports access failures instead of appearing to be an empty table.
    result = query(None, ctypes.byref(size), False, 2, 3, 0)
    if result not in {0, 122}:
        raise ManagementError("Cannot inspect listening ports; check permissions.")
    for _ in range(3):
        buffer = ctypes.create_string_buffer(max(size.value, 4))
        result = query(buffer, ctypes.byref(size), False, 2, 3, 0)
        if result == 122:
            continue
        if result != 0:
            raise ManagementError("Cannot inspect listening ports; check permissions.")
        count = wintypes.DWORD.from_buffer(buffer).value
        rows = (TcpRow * count).from_buffer(buffer, 4)
        return {
            row.pid for row in rows if socket.ntohs(row.local_port & 0xFFFF) == port
        }
    raise ManagementError("Listening ports changed during inspection; retry status.")


def read_state(data: Path) -> dict | None:
    path = data / "runtime" / STATE_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        state = json.loads(raw)
        required = {
            "pid",
            "created",
            "executable",
            "port",
            "data_directory",
            "token",
            "instance",
        }
        if not isinstance(state, dict) or not required.issubset(state):
            raise ValueError
        if (
            type(state["pid"]) is not int
            or state["pid"] <= 0
            or type(state["created"]) is not int
            or type(state["port"]) is not int
            or any(
                not isinstance(state[key], str) or not state[key]
                for key in ("executable", "data_directory", "token", "instance")
            )
        ):
            raise ValueError
        return state
    except (ValueError, TypeError):
        raise ManagementError("Runtime state is damaged; inspect it locally.") from None


def control(state: dict, action: str, *, post: bool = False) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{state['port']}/api/internal/service/{action}",
        data=b"" if post else None,
        headers={"X-Tracker-Control": state["token"]},
        method="POST" if post else "GET",
    )
    # Never send private loopback control through an environment-configured proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=3) as response:
        return json.load(response)


def lock_busy(data: Path) -> bool:
    path = data / "runtime" / LOCK_FILE
    try:
        stream = path.open("rb")
    except FileNotFoundError:
        return False
    with stream:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {13, 36}:
                return True
            raise
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    return False


@contextmanager
def management_lock(data: Path):
    runtime = data / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / LOCK_FILE).open("a+b") as stream:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {13, 36}:
                raise ManagementError(
                    "Another management operation is active.", "warning", busy=True
                ) from None
            raise
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def status(data: Path, port: int, *, check_lock: bool = True) -> dict:
    result = {
        "schema_version": 1,
        "state": "stopped",
        "detail": "No managed process or listening port was found.",
        "pid": None,
        "port": port,
        "data_directory": str(data),
    }
    try:
        if check_lock and lock_busy(data):
            raise ManagementError(
                "A management operation is active.", "warning", busy=True
            )
        state = read_state(data)
        owned = False
        if state:
            if state["port"] != port or Path(state["data_directory"]).resolve() != data:
                raise ManagementError(
                    "Instance parameters differ from runtime state.", "warning"
                )
            identity = process_identity(state["pid"])
            if identity:
                if identity["created"] != state["created"] or Path(
                    identity["executable"]
                ) != Path(state["executable"]):
                    raise ManagementError(
                        "Recorded PID belongs to another process.", "warning"
                    )
                owned = True
                result["pid"] = state["pid"]
        owners = listeners(port)
        if owners and (not owned or owners != {state["pid"]}):
            raise ManagementError(
                "Port is occupied by an unmanaged process.", "warning"
            )
        if owned:
            if not owners:
                raise ManagementError("Managed process is not listening.", "warning")
            try:
                response = control(state, "identity")
            except (OSError, ValueError, urllib.error.URLError):
                raise ManagementError(
                    "Managed process did not pass its health check.", "warning"
                ) from None
            if response != {"pid": state["pid"], "instance": state["instance"]}:
                raise ManagementError(
                    "Service identity response does not match.", "warning"
                )
            result.update(state="running", detail="Managed service is ready.")
    except ManagementError as exc:
        result.update(state=exc.state, detail=str(exc))
        if exc.busy:
            result["busy"] = True
    except (OSError, subprocess.SubprocessError):
        result.update(state="unknown", detail="Unable to inspect service state.")
    return result


def start(data: Path, port: int) -> dict:
    before = status(data, port, check_lock=False)
    if before["state"] == "running":
        return before
    if before["state"] != "stopped":
        raise ManagementError(before["detail"], before["state"])
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise ManagementError("Frontend build is missing; run pnpm build in frontend.")
    # Prevent a local-only instance from accidentally binding an already-used port
    # even when system process inspection is temporarily stale.
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise ManagementError(
                "The service port is unavailable.", "warning"
            ) from None
    logs = data / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    environment = dict(os.environ)
    environment["TRACKER_DATA_DIR"] = str(data)
    token = secrets.token_urlsafe(32)
    environment["TRACKER_CONTROL_TOKEN"] = token
    environment["PYTHONIOENCODING"] = "utf-8"
    with (
        (logs / f"tracker-{stamp}.stdout.log").open("wb") as stdout,
        (logs / f"tracker-{stamp}.stderr.log").open("wb") as stderr,
    ):
        process = subprocess.Popen(
            [str(PYTHON), "-m", "scripts.service_runner", "--port", str(port)],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        current = status(data, port, check_lock=False)
        state = read_state(data)
        if current["state"] == "running" and state and state["token"] == token:
            return current
        if process.poll() is not None:
            raise ManagementError(
                "Service exited during startup; inspect instance logs.", "warning"
            )
        time.sleep(0.25)
    raise ManagementError(
        "Startup timed out; inspect status and logs before retrying.", "warning"
    )


def stop(data: Path, port: int) -> dict:
    before = status(data, port, check_lock=False)
    if before["state"] == "stopped":
        return before
    if before["state"] != "running":
        raise ManagementError(before["detail"], before["state"])
    state = read_state(data)
    try:
        control(state, "shutdown", post=True)
    except (OSError, ValueError, urllib.error.URLError):
        raise ManagementError(
            "Graceful shutdown request failed; process was not killed.", "warning"
        ) from None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        identity = process_identity(state["pid"])
        if identity is None or identity["created"] != state["created"]:
            current = status(data, port, check_lock=False)
            if current["state"] != "stopped":
                raise ManagementError(current["detail"], current["state"])
            (data / "runtime" / STATE_FILE).unlink(missing_ok=True)
            return current
        time.sleep(0.2)
    raise ManagementError(
        "Shutdown timed out; the process was not forcibly killed.", "warning"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "restart", "status"))
    parser.add_argument("--data-path", type=Path, default=ROOT / "data")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args()
    data = options.data_path.expanduser().resolve()
    if not 1 <= options.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if options.action == "status":
        result = status(data, options.port)
        print(json.dumps(result, ensure_ascii=False))
        return int(result["state"] == "unknown")
    ok = False
    try:
        with management_lock(data):
            if options.action in {"stop", "restart"}:
                result = stop(data, options.port)
            if options.action in {"start", "restart"}:
                result = start(data, options.port)
            ok = True
    except ManagementError as exc:
        result = {
            "schema_version": 1,
            "state": exc.state,
            "detail": str(exc),
            "pid": None,
            "port": options.port,
            "data_directory": str(data),
        }
        if exc.busy:
            result["busy"] = True
    except (OSError, subprocess.SubprocessError):
        result = {
            "schema_version": 1,
            "state": "unknown",
            "detail": "Management failed; inspect permissions and instance logs.",
            "pid": None,
            "port": options.port,
            "data_directory": str(data),
        }
    if options.json:
        print(
            json.dumps(
                {**result, "action": options.action, "ok": ok}, ensure_ascii=False
            )
        )
    elif ok:
        print(result["detail"])
    if not ok:
        print(result["detail"], file=sys.stderr)
    return int(not ok)


if __name__ == "__main__":
    raise SystemExit(main())
