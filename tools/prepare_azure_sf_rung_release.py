#!/usr/bin/env python3
"""
Prepare an Azure Snowflake scale-rung model release.

By default this script is a dry-run planner. Use --execute to change
db_constants.py, validate the model, commit, and tag the release locally.
Use --push as an additional explicit step when the local release should be
pushed to GitHub.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
DATASURFACE_ROOT = Path(os.environ.get("DATASURFACE_ROOT", "/Users/billy/code/datasurface"))
DATASURFACE_PYTHON = DATASURFACE_ROOT / ".venv" / "bin" / "python"
DATASURFACE_SRC = DATASURFACE_ROOT / "src"
TAG_RE = re.compile(r"^v1\.0\.(\d+)-demo$")

sys.path.insert(0, str(TOOLS_DIR))
from set_azure_sf_stream_count import DB_CONSTANTS, _current_count, set_stream_count  # noqa: E402


def run(command: list[str], *, execute: bool, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str] | None:
    print("$ " + " ".join(command))
    if not execute:
        return None
    return subprocess.run(command, cwd=ROOT, env=env, text=True, check=True)


def git_output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def current_count() -> int:
    return _current_count(DB_CONSTANTS.read_text(encoding="utf-8"))


def ensure_clean_worktree() -> None:
    status = git_output(["git", "status", "--short"])
    if status:
        raise RuntimeError(f"Worktree is not clean:\n{status}")


def existing_demo_tags() -> list[str]:
    output = git_output(["git", "tag", "--list", "v1.0.*-demo"])
    return [line for line in output.splitlines() if line]


def next_demo_tag() -> str:
    versions = []
    for tag in existing_demo_tags():
        match = TAG_RE.match(tag)
        if match:
            versions.append(int(match.group(1)))
    next_version = max(versions, default=-1) + 1
    return f"v1.0.{next_version}-demo"


def validation_command() -> list[str]:
    return [str(DATASURFACE_PYTHON), "-m", "pytest", "test_loads.py", "-q"]


def validation_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DATASURFACE_ESO_RECONCILE"] = "false"
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(DATASURFACE_SRC) if not existing else f"{DATASURFACE_SRC}:{existing}"
    return env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("count", type=int, help="Stream count for the rung, such as 150 or 250")
    parser.add_argument("--tag", help="Release tag to create. Defaults to the next v1.0.N-demo tag.")
    parser.add_argument("--execute", action="store_true", help="Actually edit, test, commit, and tag")
    parser.add_argument("--push", action="store_true", help="Push main and the tag after --execute succeeds")
    args = parser.parse_args()

    if args.count < 1:
        raise SystemExit("count must be at least 1")
    if args.push and not args.execute:
        raise SystemExit("--push requires --execute")

    tag = args.tag or next_demo_tag()
    before = current_count()
    action = "EXECUTE" if args.execute else "DRY RUN"
    print(f"{action}: prepare Azure Snowflake {args.count}-stream release {tag}")
    print(f"Current NUM_STORES_PER_TEAM: {before}")

    if tag in existing_demo_tags():
        raise SystemExit(f"Tag already exists: {tag}")

    if not args.execute:
        print("\nPlanned local steps:")
        print(f"$ python tools/set_azure_sf_stream_count.py {args.count}")
        print("$ DATASURFACE_ESO_RECONCILE=false PYTHONPATH=/Users/billy/code/datasurface/src "
              "/Users/billy/code/datasurface/.venv/bin/python -m pytest test_loads.py -q")
        print("$ git add db_constants.py")
        print(f"$ git commit -m 'Scale Azure Snowflake model to {args.count} streams'")
        print(f"$ git tag {tag}")
        print("\nPlanned push step with --execute --push:")
        print("$ git push origin main")
        print(f"$ git push origin {tag}")
        return

    ensure_clean_worktree()
    set_stream_count(args.count)
    try:
        run(validation_command(), execute=True, env=validation_env())
        run(["git", "add", "db_constants.py"], execute=True)
        run(["git", "commit", "-m", f"Scale Azure Snowflake model to {args.count} streams"], execute=True)
        run(["git", "tag", tag], execute=True)
        if args.push:
            run(["git", "push", "origin", "main"], execute=True)
            run(["git", "push", "origin", tag], execute=True)
    except Exception:
        print(
            "\nRelease preparation failed after modifying the worktree. "
            "Inspect git status before retrying; changes were not reverted automatically.",
            file=sys.stderr,
        )
        raise


if __name__ == "__main__":
    main()
