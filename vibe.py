import os
import random
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

_paths = [p.strip() for p in os.getenv("REPO_PATHS", "").split(",") if p.strip()]
REPOS = _paths or [os.getenv("REPO_ROOT", "~").strip() or "~"]


def _env_int(key, default, floor):
    try:
        return max(floor, int(os.getenv(key, str(default))))
    except ValueError:
        return default

TICK = _env_int("UPDATE_INTERVAL", 10, 5)
IDLE_AFTER = _env_int("IDLE_SECONDS", 20, 5)
VIBE_ROTATION = _env_int("VIBE_ROTATION", 120, TICK)

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
    # pythonw has no console, so crashes would vanish silently.
    try:
        ERROR_LOG.parent.mkdir(exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} {where} ---\n")
            f.write(traceback.format_exc())
    except OSError:
        pass


def connect():
    rpc = Presence(CLIENT_ID)
    rpc.connect()
    return rpc


def rotate_if_due(now):
    # Pool rotates on its own clock, independent of verb transitions, so that
    # flipping Chatting<->Coding doesn't keep resetting the hold timer.
    if now < _vibe_cache["until"] and _vibe_cache["vibe"]:
        return
    choices = [p for p in ROTATING_POOLS if p != _vibe_cache["pool"]]
    _vibe_cache["pool"] = random.choice(choices) if choices else ROTATING_POOLS[0]
    _vibe_cache["vibe"] = next_vibe(_vibe_cache["pool"])
    _vibe_cache["until"] = now + random.uniform(VIBE_ROTATION * 0.5,
                                                VIBE_ROTATION * 2)


def tick(rpc, started, last):
    if not claude_active():
        rpc.clear()
        return "idle", None
    now = time.time()
    if started is None or last == "idle":
        started = int(now)
    gap = now - last_activity()
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

    try:
        rpc = connect()
    except (DiscordNotFound, InvalidPipe) as e:
        sys.exit(f"could not reach discord: {e}")

    started = None
    last = "idle"
    print(f"connected. updating every {TICK}s. ctrl-c to stop.")

    while True:
        try:
            last, started = tick(rpc, started, last)
            time.sleep(TICK)
        except KeyboardInterrupt:
            print()
            break
        except (PipeClosed, InvalidPipe):
            time.sleep(TICK)
            try:
                rpc = connect()
            except (DiscordNotFound, InvalidPipe):
                pass
        except Exception:
            log_error("tick")
            time.sleep(TICK)

    try:
        rpc.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
