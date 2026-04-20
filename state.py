import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
HISTORY = DATA / "history.json"

HISTORY_CAP = 1000


def append_history(entry):
    DATA.mkdir(exist_ok=True)
    try:
        log = json.loads(HISTORY.read_text(encoding="utf-8"))
        if not isinstance(log, list):
            log = []
    except (OSError, json.JSONDecodeError):
        log = []
    log.append(entry)
    HISTORY.write_text(json.dumps(log[-HISTORY_CAP:], indent=2), encoding="utf-8")
