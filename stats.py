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
    # Safety: follows no symlinks, caps depth / count / wall time, skips
    # common noise and system dirs. Returns [] on any error.
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
        )
        return int(out.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return 0


def count_total_commits(repos):
    # repos: list of paths, or a single path string. Returns total across all.
    global _commits, _repos
    now = time.time()

    if isinstance(repos, (str, Path)):
        paths = [Path(repos).expanduser()]
    elif repos:
        paths = [Path(r).expanduser() for r in repos]
    else:
        paths = []

    # If any input is a root (not itself a repo), expand via find_repos.
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
    # boundaries are .5 below the next unit so 999_999 rolls over to "1.0M"
    # instead of showing "1000k"
    if n >= 999_500_000:
        return f"{n / 1e9:.1f}B"
    if n >= 999_500:
        v = n / 1e6
        return f"{v:.0f}M" if v >= 10 else f"{v:.1f}M"
    if n >= 999.5:
        v = n / 1000
        return f"{v:.0f}k" if v >= 10 else f"{v:.1f}k"
    return str(int(n))
