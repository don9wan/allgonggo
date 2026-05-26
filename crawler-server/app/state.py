import time
from datetime import datetime, timezone
from typing import Optional

_state: dict = {
    "running": False,
    "current_source": None,
    "source_t0": None,
    "run_t0": None,
    "last_run": None,
    "db_connected": False,
    "db_last_ok_at": None,
    "startup_at": datetime.now(timezone.utc).isoformat(),
}


def mark_run_start() -> None:
    _state["running"] = True
    _state["run_t0"] = time.monotonic()
    _state["current_source"] = None


def mark_source_start(source: str) -> None:
    _state["current_source"] = source
    _state["source_t0"] = time.monotonic()


def mark_run_end(results: dict) -> None:
    elapsed = round(time.monotonic() - _state["run_t0"]) if _state["run_t0"] else None
    _state["last_run"] = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": elapsed,
        "results": results,
    }
    _state["running"] = False
    _state["current_source"] = None
    _state["source_t0"] = None
    _state["run_t0"] = None


def mark_db_ok() -> None:
    _state["db_connected"] = True
    _state["db_last_ok_at"] = datetime.now(timezone.utc).isoformat()


def mark_db_fail() -> None:
    _state["db_connected"] = False


def get_status() -> dict:
    now = time.monotonic()
    return {
        "running": _state["running"],
        "current_source": _state["current_source"],
        "current_source_elapsed_s": (
            round(now - _state["source_t0"])
            if _state["source_t0"] and _state["running"]
            else None
        ),
        "run_elapsed_s": (
            round(now - _state["run_t0"])
            if _state["run_t0"] and _state["running"]
            else None
        ),
        "last_run": _state["last_run"],
        "db_connected": _state["db_connected"],
        "db_last_ok_at": _state["db_last_ok_at"],
        "startup_at": _state["startup_at"],
    }
