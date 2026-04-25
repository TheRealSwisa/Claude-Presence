import atexit
import os
import random
import signal
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
from pypresence import Presence, PipeClosed, DiscordNotFound, InvalidPipe

from vibes import next_vibe
from stats import (count_total_commits, claude_usage_totals, format_compact,
                   last_activity, claude_active)
from state import append_history

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
LOGO = os.getenv("LARGE_IMAGE_KEY", "logo").strip()
ERROR_LOG = ROOT / "data" / "error.log"
ERROR_LOG_CAP = 256 * 1024
STOP_FILE = ROOT / "data" / "stop"

_paths = [p.strip() for p in os.getenv("REPO_PATHS", "").split(",") if p.strip()]
REPOS = _paths or [os.getenv("REPO_ROOT", "~").strip() or "~"]


def _env_int(key, default, floor):
    try:
        return max(floor, int(os.getenv(key, str(default))))
    except ValueError:
        return default

TICK = _env_int("UPDATE_INTERVAL", 15, 5)
IDLE_AFTER = _env_int("IDLE_SECONDS", 300, 30)
VIBE_ROTATION = _env_int("VIBE_ROTATION", 120, TICK)
CONNECT_DEADLINE = 60

POOL_VERBS = {
    "working": "Coding",
    "debugging": "Debugging",
    "testing": "Testing",
    "building": "Building",
    "committing": "Committing",
}
ROTATING_POOLS = list(POOL_VERBS)
_vibe_cache = {"vibe": None, "pool": None, "until": 0}


def log_error(where):
    # no console in pythonw, log crashes to file
    try:
        ERROR_LOG.parent.mkdir(exist_ok=True)
        if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > ERROR_LOG_CAP:
            tail = ERROR_LOG.read_bytes()[-ERROR_LOG_CAP // 2:]
            ERROR_LOG.write_bytes(tail)
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} [{where}]\n")
            f.write(traceback.format_exc())
    except OSError:
        pass


def connect():
    rpc = Presence(CLIENT_ID)
    rpc.connect()
    return rpc


def connect_retry(deadline):
    # discord may not be up yet at login
    while True:
        try:
            return connect()
        except (DiscordNotFound, InvalidPipe):
            if time.time() >= deadline:
                raise
            time.sleep(5)


def rotate_if_due(now):
    if now < _vibe_cache["until"] and _vibe_cache["vibe"]:
        return
    choices = [p for p in ROTATING_POOLS if p != _vibe_cache["pool"]]
    _vibe_cache["pool"] = random.choice(choices) if choices else ROTATING_POOLS[0]
    _vibe_cache["vibe"] = next_vibe(_vibe_cache["pool"])
    _vibe_cache["until"] = now + random.uniform(VIBE_ROTATION * 0.5,
                                                VIBE_ROTATION * 2)


def tick(rpc, started, last):
    now = time.time()
    gap = now - last_activity()

    # no recent file activity = not using claude
    if gap > IDLE_AFTER or not claude_active():
        if last != "idle":
            rpc.clear()
        return "idle", None

    if started is None or last == "idle":
        started = int(now)

    if gap < 30:
        verb = "Chatting"
        vibe = next_vibe("working") if _vibe_cache.get("last_verb") != "Chatting" else _vibe_cache["vibe"]
        _vibe_cache["vibe"] = vibe
    else:
        rotate_if_due(now)
        verb = POOL_VERBS[_vibe_cache["pool"]]
        vibe = _vibe_cache["vibe"]
    _vibe_cache["last_verb"] = verb

    _, tokens = claude_usage_totals()
    commits = count_total_commits(REPOS)

    line = f"{commits} commits"
    if tokens:
        line += f" · {format_compact(tokens)} tokens"

    rpc.update(
        details=f"{verb} · {vibe}"[:128],
        state=line[:128],
        large_image=LOGO,
        large_text=verb.lower(),
        start=started,
    )

    if verb != last:
        try:
            append_history({"t": int(now), "verb": verb,
                            "vibe": vibe, "commits": commits})
        except OSError:
            log_error("append_history")

    return verb, started


def main():
    if not CLIENT_ID:
        sys.exit("missing DISCORD_CLIENT_ID in .env")

    rpc = None

    def cleanup():
        nonlocal rpc
        if rpc is None:
            return
        try:
            rpc.clear()
        except Exception:
            pass
        try:
            rpc.close()
        except Exception:
            pass
        rpc = None

    def on_signal(_signum, _frame):
        cleanup()
        sys.exit(0)

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_signal)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, on_signal)

    try:
        rpc = connect_retry(time.time() + CONNECT_DEADLINE)
    except (DiscordNotFound, InvalidPipe) as e:
        sys.exit(f"could not reach discord: {e}")

    # wipe stale activity from a prior run
    try:
        rpc.clear()
    except Exception:
        pass

    started = None
    last = "idle"
    print(f"connected. updating every {TICK}s. ctrl-c to stop.")

    while True:
        try:
            if STOP_FILE.exists():
                try:
                    STOP_FILE.unlink()
                except OSError:
                    pass
                break
            last, started = tick(rpc, started, last)
            # short sleeps so stop.bat can interrupt fast
            for _ in range(TICK):
                if STOP_FILE.exists():
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            break
        except (PipeClosed, InvalidPipe):
            time.sleep(TICK)
            try:
                rpc = connect()
                rpc.clear()
                started = None
                last = "idle"
            except (DiscordNotFound, InvalidPipe):
                pass
        except Exception:
            log_error("tick")
            time.sleep(TICK)


if __name__ == "__main__":
    main()
