"""
Remembers when the agent last ran successfully, so each run only reads
emails that arrived since then.
"""

import json
import os
import time

STATE_PATH = "data/state.json"
FIRST_RUN_LOOKBACK_HOURS = 24


def load_last_run() -> int:
    """Returns the last successful run's START time (Unix seconds).
    First run (no state.json yet): looks back FIRST_RUN_LOOKBACK_HOURS."""
    if not os.path.exists(STATE_PATH):
        return int(time.time()) - FIRST_RUN_LOOKBACK_HOURS * 3600
    with open(STATE_PATH) as f:
        return json.load(f)["last_run"]


def save_last_run(timestamp: int):
    """Call only at the END of a successful run, passing the time captured at the START.
    Start-time = at-least-once: an email arriving mid-run may be seen twice, never zero times."""
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"last_run": timestamp}, f)
