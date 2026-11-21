"""O que muda entre o Linux do notebook e o Windows da máquina da RTX: caminho do Python de um venv, processo que fica
no ar depois de quem o subiu, e memória de processos (no Linux pelo /proc; no Windows pela API do sistema, com ctypes).

No Windows, a memória de um processo é o conjunto de trabalho (inclui páginas compartilhadas, ao contrário do Pss do
Linux) e não há medida de swap por processo: os números não se comparam um a um com os do notebook.
"""

import os
import signal
import subprocess

WINDOWS = os.name == "nt"


def venv_python(venv):
    return os.path.join(venv, "Scripts", "python.exe") if WINDOWS else os.path.join(venv, "bin", "python")


def spawn(argv, log_path, env=None):
    """Sobe um processo que continua no ar depois de quem o subiu, com a saída em `log_path`. Devolve o pid."""
    options = {"stdout": open(log_path, "a", encoding="utf-8"), "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL,
               "env": {**(env or os.environ), "PYTHONUTF8": "1"}}
    if not WINDOWS:
        return subprocess.Popen(argv, start_new_session=True, **options).pid
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        # Fora do job de quem chamou (um terminal que fecha leva junto os processos do job).
        return subprocess.Popen(argv, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options).pid
    except OSError:
        return subprocess.Popen(argv, creationflags=flags, **options).pid


if WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel.OpenProcess.restype = wintypes.HANDLE

    class _Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    class _Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    class _Status(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    def _counters(pid):
        handle = _kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            counters = _Counters(cb=ctypes.sizeof(_Counters))
            return counters if _kernel.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb) else None
        finally:
            _kernel.CloseHandle(handle)

    def _processes():
        """(pid, pid do pai, executável) de cada processo."""
        snapshot = _kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if snapshot in (None, wintypes.HANDLE(-1).value):
            return []
        found, entry = [], _Entry(dwSize=ctypes.sizeof(_Entry))
        try:
            ok = _kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                found.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
                ok = _kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            _kernel.CloseHandle(snapshot)
        return found

    def pids_named(prefix):
        """Pids dos processos cujo executável começa por `prefix` (sem contar maiúsculas)."""
        return [pid for pid, _, exe in _processes() if exe.casefold().startswith(prefix.casefold())]

    def tree(pid):
        """`pid` e seus descendentes. O python.exe de um venv no Windows é um lançador: o interpretador de verdade
        é um processo filho dele."""
        children = {}
        for child, parent, _ in _processes():
            children.setdefault(parent, []).append(child)
        found, pending = [], [pid]
        while pending:
            current = pending.pop()
            if current not in found:
                found.append(current)
                pending += children.get(current, [])
        return found


def stop(pid):
    """Encerra o processo e, no Windows, os filhos dele (ver `tree`)."""
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)


def memory_mb(pid):
    """(RAM, swap) de um processo em MB; (0, 0) se ele não existe ou não pode ser lido."""
    if WINDOWS:
        counters = _counters(pid)
        return (counters.WorkingSetSize / 2**20, 0.0) if counters else (0.0, 0.0)
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            kb = {line.split(":")[0]: int(line.split()[1]) for line in f if line.startswith(("Pss:", "SwapPss:"))}
    except (OSError, ValueError, IndexError):
        return 0.0, 0.0
    return kb.get("Pss", 0) / 1024, kb.get("SwapPss", 0) / 1024


def peak_mb():
    """Pico de memória deste processo, em MB."""
    if WINDOWS:
        counters = _counters(os.getpid())
        return counters.PeakWorkingSetSize // 2**20 if counters else 0
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024


def available_mb():
    if WINDOWS:
        status = _Status(dwLength=ctypes.sizeof(_Status))
        _kernel.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullAvailPhys / 2**20
    with open("/proc/meminfo") as f:
        return next(int(line.split()[1]) for line in f if line.startswith("MemAvailable:")) / 1024
