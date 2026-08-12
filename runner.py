"""Command line runner for OrchestraBench tasks."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml


PROJECT_DIR = Path(__file__).resolve().parent
TASKS_DIR = PROJECT_DIR / "tasks"
REPORT_PATH = PROJECT_DIR / "traces" / "latest_run.json"


def discover_tasks(tasks_dir: Path = TASKS_DIR) -> list[Path]:
    """Return task directories containing a metadata.yaml file."""
    if not tasks_dir.is_dir():
        return []
    return sorted(
        (path.parent for path in tasks_dir.glob("*/metadata.yaml")),
        key=lambda path: path.name,
    )


def load_metadata(task_dir: Path) -> dict[str, Any]:
    """Load a task's metadata, treating an empty YAML document as empty data."""
    with (task_dir / "metadata.yaml").open(encoding="utf-8") as metadata_file:
        metadata = yaml.safe_load(metadata_file) or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata.yaml must contain a mapping")
    return metadata


def run_task(task_dir: Path) -> dict[str, Any]:
    """Run one task and return its result record."""
    metadata = load_metadata(task_dir)
    command = metadata.get("test_command", "")
    start = time.perf_counter()
    if command:
        completed = subprocess.run(
            command,
            cwd=task_dir,
            shell=True,
            capture_output=True,
            text=True,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    else:
        returncode = 1
        stdout = ""
        stderr = "metadata.yaml does not define test_command"

    return {
        "task_id": metadata.get("task_id", task_dir.name),
        "name": metadata.get("name", task_dir.name),
        "domain": metadata.get("domain"),
        "difficulty": metadata.get("difficulty"),
        "passed": returncode == 0,
        "returncode": returncode,
        "runtime_seconds": time.perf_counter() - start,
        "stdout": stdout,
        "stderr": stderr,
        "ao_metrics": metadata.get("ao_metrics", {}),
        "traceability": metadata.get("traceability", {}),
    }


def write_report(results: list[dict[str, Any]], report_path: Path = REPORT_PATH) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as report_file:
        json.dump(results, report_file, indent=2)
        report_file.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run OrchestraBench tasks")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="run all tasks")
    selection.add_argument("--task", metavar="TASK_ID", help="run one task")
    args = parser.parse_args(argv)

    task_dirs = discover_tasks()
    if not task_dirs:
        print("No tasks found.")
        write_report([])
        return 0

    if args.task:
        matching_tasks = []
        for task_dir in task_dirs:
            metadata = load_metadata(task_dir)
            task_id = metadata.get("task_id", task_dir.name)
            if task_id == args.task:
                matching_tasks.append(task_dir)
        task_dirs = matching_tasks
        if not task_dirs:
            print(f"Task not found: {args.task}")
            return 1

    results = [run_task(task_dir) for task_dir in task_dirs]
    write_report(results)
    print(f"Completed {len(results)} task(s).")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
