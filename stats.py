import json
import os
import subprocess
import time
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude" / "projects"
TTL = 30
SCAN_TTL = 300
SCAN_MAX_DEPTH = 6
SCAN_MAX_REPOS = 200
SCAN_TIMEOUT = 10

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".next",
             "dist", "build", ".cache", "target", ".gradle", "Library",
             "AppData", "Applications", "Program Files", "Program Files (x86)",
             "Windows", "System32", "snap", "flatpak"}

_files = {}
_totals = None
_commits = None
_repos = None


def find_repos(root):
    # walk the tree looking for .git folders. bails on symlinks, depth,
    # count, or wall time to stay cheap.
    root = Path(root).expanduser()
    if not root.exists():
        return []
    root = root.resolve()
    found = []
    stack = [(root, 0)]
    deadline = time.time() + SCAN_TIMEOUT

    while stack:
        if len(found) >= SCAN_MAX_REPOS or time.time() > deadline:
            break
        d, depth = stack.pop()
        if depth > SCAN_MAX_DEPTH:
            continue
        try:
            entries = list(os.scandir(d))
        except (OSError, PermissionError):
            continue
        if any(e.name == ".git" and e.is_dir(follow_symlinks=False)
               for e in entries):
            found.append(Path(d))
            continue
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            if e.name in SKIP_DIRS or e.name.startswith("."):
                continue
            stack.append((e.path, depth + 1))
    return found


def _git_count(repo):
    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return int(out.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return 0


def count_total_commits(repos):
    global _commits, _repos
    now = time.time()

    if isinstance(repos, (str, Path)):
        paths = [Path(repos).expanduser()]
    elif repos:
        paths = [Path(r).expanduser() for r in repos]
    else:
        paths = []

    expanded = []
    for p in paths:
        if (p / ".git").is_dir():
            expanded.append(p)
        else:
            if not _repos or now - _repos[0] > SCAN_TTL:
                _repos = (now, find_repos(p))
            expanded.extend(_repos[1])

    key = tuple(sorted(str(p) for p in expanded))
    if _commits and _commits[1] == key and now - _commits[0] < TTL:
        return _commits[2]

    total = sum(_git_count(r) for r in expanded)
    _commits = (now, key, total)
    return total


def last_activity(root=CLAUDE_DIR):
    newest = 0
    if not root.exists():
        return 0
    for path in root.rglob("*.jsonl"):
        try:
            m = path.stat().st_mtime
        except OSError:
            continue
        if m > newest:
            newest = m
    return newest


def _sum_file(path):
    msgs = tokens = 0
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    msg = json.loads(line).get("message")
                except json.JSONDecodeError:
                    continue
                u = msg.get("usage") if isinstance(msg, dict) else None
                if not isinstance(u, dict):
                    continue
                msgs += 1
                tokens += (u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
    except OSError:
        pass
    return msgs, tokens


def claude_usage_totals(root=CLAUDE_DIR):
    global _totals
    now = time.time()
    if _totals and now - _totals[0] < TTL:
        return _totals[1], _totals[2]

    m_total = t_total = 0
    if root.exists():
        for path in root.rglob("*.jsonl"):
            try:
                st = path.stat()
            except OSError:
                continue
            key = (st.st_mtime, st.st_size)
            cached = _files.get(path)
            if cached and cached[:2] == key:
                m, t = cached[2], cached[3]
            else:
                m, t = _sum_file(path)
                _files[path] = (*key, m, t)
            m_total += m
            t_total += t

    _totals = (now, m_total, t_total)
    return m_total, t_total


def format_compact(n):
    # roll over .5 early so 999_999 shows "1.0M" instead of "1000k"
    if n >= 999_500_000:
        return f"{n / 1e9:.1f}B"
    if n >= 999_500:
        v = n / 1e6
        return f"{v:.0f}M" if v >= 10 else f"{v:.1f}M"
    if n >= 999.5:
        v = n / 1000
        return f"{v:.0f}k" if v >= 10 else f"{v:.1f}k"
    return str(int(n))


# ---- windows window-state detection ----------------------------------------
# used to tell if claude is actually up on screen (desktop window visible, or
# a terminal hosting the claude-code cli is visible). on non-windows we just
# assume yes.

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD,
        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    _TH32CS_SNAPPROCESS = 0x00000002

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _kernel32.CreateToolhelp32Snapshot.argtypes = [
        wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel32.Process32NextW.restype = wintypes.BOOL


def _image_path(pid):
    h = _kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        _kernel32.CloseHandle(h)
    return ""


def _proc_tree():
    tree = {}
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return tree
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if _kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                tree[entry.th32ProcessID] = (
                    entry.th32ParentProcessID,
                    entry.szExeFile.lower(),
                )
                if not _kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
    finally:
        _kernel32.CloseHandle(snap)
    return tree


_TERMINAL_EXES = {
    "windowsterminal.exe", "conhost.exe", "openconsole.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe",
    "wezterm-gui.exe", "wezterm.exe",
    "alacritty.exe", "mintty.exe", "bash.exe",
    "tabby.exe", "hyper.exe",
}


def claude_active():
    if os.name != "nt":
        return True

    visible = set()

    def cb(hwnd, _lp):
        if _user32.IsWindowVisible(hwnd) and not _user32.IsIconic(hwnd):
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                visible.add(pid.value)
        return True

    _user32.EnumWindows(_EnumWindowsProc(cb), 0)
    if not visible:
        return False

    # claude desktop window up?
    for pid in visible:
        p = _image_path(pid).lower()
        if p.endswith("\\claude.exe") and "windowsapps" in p:
            return True

    # claude-code cli inside a visible terminal?
    tree = _proc_tree()
    for pid, (_parent, name) in tree.items():
        if name != "claude.exe":
            continue
        if "claude-code" not in _image_path(pid).lower():
            continue
        cur = tree.get(pid, (0, ""))[0]
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            parent, pname = tree.get(cur, (0, ""))
            if pname in _TERMINAL_EXES and cur in visible:
                return True
            cur = parent
    return False
