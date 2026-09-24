"""Windows AppContainer + Job Object isolation for skill scripts.

Scripts keep a normal Python process, but the process identity can only use
paths we grant and has no network capability. If the container cannot be
created, the caller must refuse to run the script.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

_PROFILE_NAME = "OfficeAgent.ScriptJail"
_granted: set[tuple[str, str]] = set()


class ScriptIsolationError(RuntimeError):
    pass


def windows_isolation_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        ctypes.WinDLL("userenv")
        ctypes.WinDLL("kernel32")
        return True
    except OSError:
        return False


def _raise_last(prefix: str) -> None:
    err = ctypes.get_last_error()
    raise ScriptIsolationError(f"{prefix} (winerror {err})")


def _sid_string(sid: int) -> str:
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    out = ctypes.c_wchar_p()
    if not advapi.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(out)):
        _raise_last("ConvertSidToStringSidW failed")
    text = out.value or ""
    kernel.LocalFree(out)
    if not text:
        raise ScriptIsolationError("empty AppContainer SID")
    return text


def _container_sid() -> tuple[int, str]:
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    userenv.CreateAppContainerProfile.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.CreateAppContainerProfile.restype = wintypes.LONG
    userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    userenv.DeriveAppContainerSidFromAppContainerName.restype = wintypes.LONG
    sid = ctypes.c_void_p()
    hr = userenv.CreateAppContainerProfile(
        _PROFILE_NAME,
        "Office Agent Script Jail",
        "Workspace-scoped script process",
        None,
        0,
        ctypes.byref(sid),
    )
    # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS) == 0x800700B7
    if hr == -2147024713 or (hr & 0xFFFFFFFF) == 0x800700B7:
        hr = userenv.DeriveAppContainerSidFromAppContainerName(_PROFILE_NAME, ctypes.byref(sid))
    if hr < 0 or not sid.value:
        raise ScriptIsolationError(f"CreateAppContainerProfile failed (hr {hr})")
    return int(sid.value), _sid_string(int(sid.value))


def _grant(path: Path, sid: str, rights: str) -> None:
    key = (str(path), rights)
    if key in _granted or not path.exists():
        _granted.add(key)
        return
    subprocess.run(
        ["icacls", str(path), "/grant", f"*{sid}:{rights}", "/T", "/C", "/Q"],
        check=False,
        capture_output=True,
    )
    _granted.add(key)


def _grant_roots(sid: str, read_roots: list[Path], write_roots: list[Path]) -> None:
    for root in read_roots:
        _grant(root, sid, "(OI)(CI)(GR)")
    for root in write_roots:
        _grant(root, sid, "(OI)(CI)(M)")


class _SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.c_void_p),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _bind_job(process: int) -> None:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        _raise_last("CreateJobObjectW failed")

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [("x", ctypes.c_uint64)] * 6

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        _raise_last("SetInformationJobObject failed")
    if not kernel.AssignProcessToJobObject(job, process):
        _raise_last("AssignProcessToJobObject failed")


def run_in_appcontainer(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    read_roots: list[Path],
    write_roots: list[Path],
) -> subprocess.CompletedProcess[str]:
    """Run cmd inside an AppContainer with no network capability."""
    if not windows_isolation_available():
        raise ScriptIsolationError("Windows AppContainer APIs are unavailable")
    sid_ptr, sid_text = _container_sid()
    _grant_roots(sid_text, read_roots, write_roots)

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_NO_WINDOW = 0x08000000
    STARTF_USESTDHANDLES = 0x00000100
    PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
    HANDLE_FLAG_INHERIT = 0x00000001

    def _pipe() -> tuple[int, int]:
        read = wintypes.HANDLE()
        write = wintypes.HANDLE()
        if not kernel.CreatePipe(ctypes.byref(read), ctypes.byref(write), None, 0):
            _raise_last("CreatePipe failed")
        kernel.SetHandleInformation(write, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
        return int(read.value or 0), int(write.value or 0)

    out_r, out_w = _pipe()
    err_r, err_w = _pipe()

    size = ctypes.c_size_t(0)
    kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attr = ctypes.create_string_buffer(size.value)
    if not kernel.InitializeProcThreadAttributeList(attr, 1, 0, ctypes.byref(size)):
        _raise_last("InitializeProcThreadAttributeList failed")
    caps = _SECURITY_CAPABILITIES(AppContainerSid=sid_ptr, Capabilities=None, CapabilityCount=0, Reserved=0)
    if not kernel.UpdateProcThreadAttribute(
        attr,
        0,
        PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
        ctypes.byref(caps),
        ctypes.sizeof(caps),
        None,
        None,
    ):
        _raise_last("UpdateProcThreadAttribute failed")

    si = _STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(si)
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    si.StartupInfo.hStdOutput = out_w
    si.StartupInfo.hStdError = err_w
    si.lpAttributeList = ctypes.cast(attr, ctypes.c_void_p)
    pi = _PROCESS_INFORMATION()

    cmdline = subprocess.list2cmdline(cmd)
    env_block = "\0".join(f"{k}={v}" for k, v in env.items()) + "\0\0"
    ok = kernel.CreateProcessW(
        None,
        ctypes.c_wchar_p(cmdline),
        None,
        None,
        True,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW,
        ctypes.c_wchar_p(env_block),
        str(cwd),
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    kernel.DeleteProcThreadAttributeList(attr)
    kernel.CloseHandle(out_w)
    kernel.CloseHandle(err_w)
    if not ok:
        _raise_last("CreateProcessW failed")
    _bind_job(int(pi.hProcess))
    kernel.ResumeThread(pi.hThread)
    wait = kernel.WaitForSingleObject(pi.hProcess, int(timeout * 1000))
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    kernel.CloseHandle(pi.hThread)
    kernel.CloseHandle(pi.hProcess)

    def _read(handle: int) -> str:
        data = bytearray()
        buf = ctypes.create_string_buffer(4096)
        n = wintypes.DWORD()
        while kernel.ReadFile(handle, buf, 4096, ctypes.byref(n), None) and n.value:
            data.extend(buf.raw[: n.value])
        kernel.CloseHandle(handle)
        return data.decode("utf-8", errors="replace")

    stdout = _read(out_r)
    stderr = _read(err_r)
    if wait == 0x00000102:  # WAIT_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(cmd, int(code.value), stdout, stderr)
