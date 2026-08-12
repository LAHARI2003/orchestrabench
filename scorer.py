"""Score a run produced by :mod:`orchestrabench.runner`.

The scorer deliberately does not depend on the runner implementation.  A run is
expected to contain a ``tasks`` list (a bare list is accepted too), with one
small dictionary per task.  A few aliases are accepted so that hand-written
demo traces remain convenient to use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TRACE_PATH = Path("traces/latest_run.json")


def _value(item: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _percent(value: Any) -> float:
    """Turn either a 0..1 or a 0..100 score into a percentage."""
    number = _number(value)
    return max(0.0, min(100.0, number * 100 if number <= 1 else number))


def _tasks(trace: Any) -> list[dict[str, Any]]:
    if isinstance(trace, list):
        source = trace
    elif isinstance(trace, dict):
        source = trace.get("tasks", trace.get("results", []))
    else:
        source = []
    return [task for task in source if isinstance(task, dict)]


def score_trace(trace: Any) -> dict[str, float | int]:
    """Return the six requested metrics and the weighted score.

    Rates are percentages (0--100); averages retain their natural units.
    Missing counters are treated as zero, which makes the format pleasant for
    small synthetic traces and, importantly, keeps empty runs safe.
    """
    tasks = _tasks(trace)
    total = len(tasks)

    def success(task: dict[str, Any]) -> bool:
        status = str(_value(task, "status", "result", default="")).lower()
        explicit = _value(task, "success", "succeeded")
        return _flag(explicit) if explicit is not None else status in {
            "success", "succeeded", "passed", "complete", "completed", "ok"
        }

    successes = sum(success(task) for task in tasks)
    failures = total - successes
    recovered = sum(
        _flag(_value(task, "autonomous_recovery", "recovered", "recovery", default=False))
        for task in tasks
        if not success(task)
    )

    human_touches = sum(
        _number(_value(task, "human_touches", "human_touch_count", "touches", default=0))
        for task in tasks
    )
    ci_runs = sum(_number(_value(task, "ci_runs", "ci_run_count", default=0)) for task in tasks)
    collisions = sum(
        _flag(_value(task, "worktree_collision", "collision", "worktree_collided", default=False))
        for task in tasks
    )

    traceability_values = []
    for task in tasks:
        value = _value(task, "traceability_score", "traceability", "traceable")
        if value is not None:
            traceability_values.append(_percent(value) if not isinstance(value, bool) else (100.0 if value else 0.0))

    task_success_rate = 100.0 * successes / total if total else 0.0
    # With no failures, recovery was not needed and should not penalize a run.
    recovery_rate = 100.0 * recovered / failures if failures else 100.0
    average_human_touches = human_touches / total if total else 0.0
    average_ci_runs = ci_runs / total if total else 0.0
    collision_rate = 100.0 * collisions / total if total else 0.0
    traceability_score = sum(traceability_values) / len(traceability_values) if traceability_values else 0.0

    # Lower is better for the three operational counters.  The simple
    # reciprocal curves are bounded, explainable, and work for any trace size.
    ci_efficiency = 100.0 / max(1.0, average_ci_runs)
    low_human_touch_score = 100.0 / (1.0 + average_human_touches)
    low_collision_score = 100.0 - collision_rate
    final_score = (
        task_success_rate * 0.35
        + recovery_rate * 0.20
        + ci_efficiency * 0.15
        + low_human_touch_score * 0.10
        + low_collision_score * 0.10
        + traceability_score * 0.10
    )

    return {
        "task_success_rate": round(task_success_rate, 2),
        "autonomous_recovery_rate": round(recovery_rate, 2),
        "average_human_touches": round(average_human_touches, 2),
        "average_ci_runs": round(average_ci_runs, 2),
        "worktree_collision_rate": round(collision_rate, 2),
        "traceability_score": round(traceability_score, 2),
        "final_score": round(final_score, 2),
    }


def main() -> int:
    if not TRACE_PATH.exists():
        print("No trace found. Run this first:")
        print("python -m orchestrabench.runner --all")
        return 1
    try:
        with TRACE_PATH.open(encoding="utf-8") as stream:
            trace = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read {TRACE_PATH}: {exc}")
        return 1
    print(json.dumps(score_trace(trace), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
